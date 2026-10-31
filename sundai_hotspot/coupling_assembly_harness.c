/*
 * SentiLab SLAB-049: conductance-assembly harness. It is not part of the HotSpot binary.
 *
 * It builds a grid model the way hotspot.c does (config file, LCF, -model_type grid, -detailed_3D on),
 * populates the R model, and reports:
 *   - the find_res() vertical resistance for every adjacent layer pair at one probe cell,
 *   - the heatsink cell's link to ambient,
 *   - the assembled steady-state conductance matrix that direct_SLU() factorizes
 *     (build_transient_grid_matrix), written as raw CSC arrays.
 * It never solves: no dgssv, no steady_state_temp, no temperatures.
 *
 * usage: coupling_assembly_harness <config> <lcf> <rows> <cols> <r_convec> <probe_row> <probe_col> <matrix_out>
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "util.h"
#include "flp.h"
#include "materials.h"
#include "microchannel.h"
#include "temperature.h"
#include "temperature_grid.h"
#include "slu_ddefs.h"

double find_res(grid_model_t *model, int n1, int i1, int j1, int n2, int i2, int j2);

static void set_pair(str_pair *pair, const char *name, const char *value)
{
  strncpy(pair->name, name, STR_SIZE - 1);
  pair->name[STR_SIZE - 1] = '\0';
  strncpy(pair->value, value, STR_SIZE - 1);
  pair->value[STR_SIZE - 1] = '\0';
}

int main(int argc, char **argv)
{
  str_pair table[MAX_ENTRIES];
  int size = 0;
  materials_list_t materials_list;
  thermal_config_t thermal_config;
  RC_model_t *model;
  grid_model_t *g;
  SuperMatrix A;
  NCformat *store;
  FILE *out;
  int n, l, i, j, nl, hsidx, spidx;

  if (argc != 9) {
    fprintf(stderr, "usage: %s <config> <lcf> <rows> <cols> <r_convec> <probe_row> <probe_col> <matrix_out>\n", argv[0]);
    return 2;
  }
  i = atoi(argv[6]);
  j = atoi(argv[7]);

  /* Earlier entries override later ones, as in hotspot.c: command-line style overrides first. */
  set_pair(&table[size++], "grid_layer_file", argv[2]);
  set_pair(&table[size++], "model_type", "grid");
  set_pair(&table[size++], "grid_rows", argv[3]);
  set_pair(&table[size++], "grid_cols", argv[4]);
  set_pair(&table[size++], "r_convec", argv[5]);
  size += read_str_pairs(&table[size], MAX_ENTRIES - size, argv[1]);
  size = str_pairs_remove_duplicates(table, size);

  default_materials(&materials_list);
  thermal_config = default_thermal_config();
  thermal_config_add_from_strs(&thermal_config, &materials_list, table, size);

  model = alloc_RC_model(&thermal_config, NULL, NULL, &materials_list, TRUE, FALSE);
  if (model->type != GRID_MODEL || !model->grid->has_lcf || !model->grid->config.detailed_3D_used)
    fatal("harness requires a detailed 3D grid model with an LCF\n");
  populate_R_model(model, NULL);

  g = model->grid;
  nl = g->n_layers;
  spidx = nl - DEFAULT_PACK_LAYERS + LAYER_SP;
  hsidx = nl - DEFAULT_PACK_LAYERS + LAYER_SINK;
  if (i < 0 || i >= g->rows || j < 0 || j >= g->cols)
    fatal("probe cell outside the grid\n");

  printf("layers %d spreader %d sink %d rows %d cols %d\n", nl, spidx, hsidx, g->rows, g->cols);
  printf("cell_width %.17g cell_height %.17g\n", g->width / g->cols, g->height / g->rows);
  printf("r_convec %.17g s_sink %.17g s_spreader %.17g\n",
         g->config.r_convec, g->config.s_sink, g->config.s_spreader);
  for (l = 0; l < nl; l++)
    printf("layer %d k %.17g thickness %.17g rz %.17g\n", l, g->layers[l].k, g->layers[l].thickness, g->layers[l].rz);
  for (l = 0; l + 1 < nl; l++)
    printf("vertical %d %d %.17g\n", l, l + 1, find_res(g, l + 1, i, j, l, i, j));
  printf("sink_ambient %.17g\n", find_res_3D(hsidx, i, j, g, 3));

  A = build_transient_grid_matrix(g);
  store = (NCformat *) A.Store;
  n = A.ncol;
  out = fopen(argv[8], "wb");
  if (!out)
    fatal("cannot open matrix output\n");
  /* Header: matrix order, nonzero count and the byte width of the SuperLU index type. */
  {
    int header[3];
    header[0] = n;
    header[1] = (int) store->nnz;
    header[2] = (int) sizeof(*store->colptr);
    fwrite(header, sizeof(int), 3, out);
  }
  fwrite(store->colptr, sizeof(*store->colptr), (size_t) n + 1, out);
  fwrite(store->rowind, sizeof(*store->rowind), (size_t) store->nnz, out);
  fwrite(store->nzval, sizeof(double), (size_t) store->nnz, out);
  fclose(out);
  printf("matrix n %d nnz %d\n", n, (int) store->nnz);

  Destroy_CompCol_Matrix(&A);
  return 0;
}
