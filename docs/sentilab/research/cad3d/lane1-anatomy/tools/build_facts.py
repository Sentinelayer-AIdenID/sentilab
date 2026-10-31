"""Write evidence/<lane>/FACTS.jsonl for lane1-anatomy from the fact table below.

Usage: python -I build_facts.py <evidence_root>
URL and retrieval time are filled from evidence/FETCHLOG.tsv by evidence file stem.
"""
import csv
import json
import os
import sys

ROOT = sys.argv[1]

# slug -> (title, publisher/author, date, source_type)
SRC = {
    # HBM / interfaces
    "jedec_hbm3_pr_2022": ("JEDEC Publishes HBM3 Update to High Bandwidth Memory (HBM) Standard (JESD238)", "JEDEC", "2022-01-27", "primary"),
    "jedec_hbm4_pr_2025": ("JEDEC and Industry Leaders Collaborate to Release JESD270-4 HBM4 Standard", "JEDEC", "2025-04-16", "primary"),
    "trendforce_hbm4_775um_2025": ("JEDEC Finalizes HBM4 Standard, Potentially Easing Pressure on Hybrid Bonding Adoption (citing ZDNet)", "TrendForce", "2025-04-21", "secondary"),
    "skhynix_hbm3e_12h_2024": ("SK hynix Begins Volume Production of the World's First 12-Layer HBM3E", "SK hynix Newsroom", "2024-09-26", "primary"),
    "samsung_hbm3e_12h_2024": ("Samsung Develops Industry-First 36GB HBM3E 12H DRAM", "Samsung Global Newsroom", "2024-02-27", "primary"),
    "micron_hbm3e_product_brief": ("Product Brief - Micron HBM3E (Rev C 10/2023)", "Micron Technology", "2023-10", "primary"),
    "skhynix_hc28_hbm_tutorial": ("The Era of High Bandwidth Memory (K. Tran, Hot Chips 28 tutorial)", "SK hynix / Hot Chips", "2016-08", "primary"),
    "formfactor_swtw2016_hbm_probing": ("Verification of HBM through Direct Probing on MicroBumps (M. Loranger, SWTW 2016)", "FormFactor / SW Test Workshop", "2016-06", "primary"),
    "skhynix_iedm23_hbm_packaging": ("Advanced Packaging Technologies in Memory Applications for Future Generative AI Era (K.-I. Moon, H.-Y. Son, K. Lee; IEDM 2023 paper 15-6 handout)", "SK hynix / IEEE IEDM", "2023-12", "primary"),
    "imaps_hbm_underfill_tsv_study": ("A Study on the Effectiveness of Underfill in the High Bandwidth Memory with TSV (W.-S. Lee et al., IMAPS 2013)", "IMAPS (authors from SK hynix)", "2013-10", "primary"),
    "samsung_12layer_3dtsv_2019": ("Samsung Electronics Develops Industry's First 12-Layer 3D-TSV Chip Packaging Technology", "Samsung Global Newsroom", "2019-10-07", "primary"),
    "skhynix_tsmc_hbm4_mou_2024": ("SK hynix Partners with TSMC to Strengthen HBM Technological Leadership", "SK hynix Newsroom", "2024-04-19", "primary"),
    "tomshw_skhynix_hbm4_16hi": ("SK hynix shows 16-Hi HBM4 memory for AI accelerators", "Tom's Hardware", "2026-01", "secondary"),
    "synopsys_hbm3_phy_page": ("HBM3 PHY IP (product page)", "Synopsys", "accessed 2026-10-31", "primary"),
    "rambus_hbm3e_controller_page": ("HBM3E Controller (product page)", "Rambus", "accessed 2026-10-31", "primary"),
    "cadence_hbm3_phy_page": ("HBM3 PHY (product page)", "Cadence", "accessed 2026-10-31", "primary"),
    "ucie_hc2023_electrical": ("UCIe Electrical, Form Factor and Compliance (Hot Chips 2023 tutorial)", "UCIe Consortium / Hot Chips", "2023-08", "primary"),
    "ucie_buss25_dassharma": ("UCIe (D. Das Sharma), IEEE Build-Up Substrate Symposium BUSS'25", "Intel / UCIe Consortium / IEEE", "2025-05-08", "primary"),
    "broadcom_stratadnx_hbm_appnote": ("StrataDNX HBM Configuration and Debugging Guide (DNX-HBM-AN101-PUB)", "Broadcom", "2021-12-10", "primary"),
    # packaging
    "tsmc_cowos_page": ("CoWoS (3DFabric technology page)", "TSMC", "accessed 2026-10-31", "primary"),
    "tsmc_soic_page": ("TSMC-SoIC (3DFabric technology page)", "TSMC", "accessed 2026-10-31", "primary"),
    "tsmc_hotchips33_packaging_tutorial": ("TSMC Packaging Technologies for Chiplets and 3D (Hot Chips 33 tutorial)", "TSMC / Hot Chips", "2021-08-19", "primary"),
    "xilinx_cpmt1104b": ("Stacked Silicon Interconnect Technology (Xilinx; IEEE CPMT chapter presentation)", "Xilinx / IEEE CPMT", "2011-04-28", "primary"),
    "xilinx_wp380": ("Xilinx Stacked Silicon Interconnect Technology Delivers Breakthrough FPGA Capacity, Bandwidth, and Power Efficiency (WP380)", "Xilinx / AMD", "2012", "primary"),
    "amkor_fcbga_ds831": ("Flip Chip BGA (FCBGA) data sheet DS831", "Amkor Technology", "accessed 2026-10-31", "primary"),
    "amkor_flipchip_ts102": ("Flip Chip Packaging technology sheet TS102", "Amkor Technology", "accessed 2026-10-31", "primary"),
    "kyocera_fcbga_organic_substrates": ("Package Substrate Solutions - FCBGA Technology (roadmap)", "Kyocera Europe", "2024", "primary"),
    "intel_qr_vol6_adv_packaging": ("Quality & Reliability Vol. 6: Intel Advanced Packaging Technology", "Intel", "accessed 2026-10-31", "primary"),
    "tsmc_patent_us20200381391_cowos": ("US20200381391A1 CoWoS Structures and Methods Forming Same (Google Patents)", "TSMC (assignee)", "2020", "primary"),
    "google_patent_us10083920_stiffener": ("US10083920B1 Package stiffener for protecting semiconductor die (Google Patents)", "Google LLC (assignee)", "2018", "primary"),
    "vicor_vpd_genai_article": ("High-Current-Density Power Modules Mitigate the Environmental Impact of Power-Intensive GenAI", "Vicor", "accessed 2026-10-31", "primary"),
    "mediaupdate_iedm2019_part2": ("IEDM 2019 (Part 2): 3D Packaging Innovation and Memory Technology (blog report of TSMC iCap paper)", "mediaupdate2019 (blog)", "2019-12-31", "secondary"),
    "tomshw_abf_substrates_2026": ("The state of ABF substrates in data center silicon in 2026", "Tom's Hardware", "2026", "secondary"),
    "microchip_fcbga196_c04_25015": ("196-Ball FCBGA 15x15x1.4 mm package drawing C04-25015 Rev A", "Microchip Technology", "2021", "primary"),
    "renesas_alg784_fcbga_29mm": ("ALG 784 package outline, FCBGA 29.0 x 29.0 mm body, 1.00 mm ball pitch (flat lid), PSC-4627", "IDT / Renesas", "2015-11-18", "primary"),
    # thermal
    "tap25d_date2021": ("TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems (Y. Ma et al., DATE 2021)", "Boston University / DATE", "2021", "primary"),
    "hotspot60_tr_https": ("HotSpot 6.0: Validation, Acceleration and Extension (R. Zhang, M. Stan, K. Skadron; UVA TR CS-2015-04)", "University of Virginia", "2015", "primary"),
    "imaps_xilinx_thermal_tsv_interposer": ("Advanced Thermal Study of Very High Power TSV Interposer and Interconnects for 28nm Technology FPGA (B. Banijamali, S. Ramalingam, R. Chaware; IMAPS 2011)", "Xilinx / IMAPS", "2011-10", "primary"),
    "ecool_si_thermal_conductivity_1998": ("The thermal conductivity of silicon", "Electronics Cooling magazine", "1998-05", "secondary"),
    "ioffe_si_thermal_http": ("Thermal properties of Silicon (Si), NSM Archive", "Ioffe Institute", "accessed 2026-10-31", "primary"),
    "indium_tim_products_page": ("Thermal Interface Materials (product page)", "Indium Corporation", "accessed 2026-10-31", "primary"),
    "indium_hp_tims_handout": ("High-Performance Thermal Interface Materials handout 99541 R1", "Indium Corporation", "2025-09", "primary"),
    "solstice_ptm7950_tds": ("PTM7950 Phase Change Material technical data sheet", "Solstice Advanced Materials (formerly Honeywell)", "accessed 2026-10-31", "primary"),
    "krayden_uf8807": ("LOCTITE ECCOBOND UF 8807 (distributor product page)", "Krayden / CAPLINQ (Henkel product)", "accessed 2026-10-31", "secondary"),
    "sumikon_g700l": ("SUMIKON EME-G700LA Type L typical properties", "Sumitomo Bakelite (mirrored by mirrorsemi.com)", "accessed 2026-10-31", "primary"),
    "solderconnection_sac305": ("PURALLOY SAC305 lead-free solid feed wire (product page)", "Solder Connection", "accessed 2026-10-31", "primary"),
    "ucla_embedded_isolators_2p5d": ("Optimizing Thermal Performance in 2.5D Systems Using Embedded Isolators (G. Karfakis et al., UCLA / Georgia Tech; author-hosted)", "UCLA NanoCAD", "2025", "primary"),
    "itherm2024_dual_sided_bspdn": ("Thermal Analysis of Dual-sided Cooling for Backside Power Delivery Networks on 2.5D Glass/Silicon Interposer Package (F. Xie, S. Lyu, T. Wei; ITherm 2024, author-hosted revised version)", "Purdue University / IEEE ITherm", "2024", "primary"),
    "ieee_spectrum_hbm_on_gpu_imec": ("HBM on GPU: Thermal Challenges and Solutions (reporting imec, IEDM 2025)", "IEEE Spectrum", "2026", "secondary"),
    "vertiv_coolant_temp_roadmap": ("Keep it at 30C: A roadmap for the future chip coolant temperature (blog)", "Vertiv", "2026", "secondary"),
    "iceotope_1000w_whitepaper": ("Chip cooling at 1000W and beyond (whitepaper page)", "Iceotope", "accessed 2026-10-31", "primary"),
    "ocp_oai_liquid_cooling_guidelines": ("OAI System Liquid Cooling Guidelines (Mar 2023 update)", "Open Compute Project", "2023-03-03", "primary"),
    "ecool_lidded_vs_bare_die_2012": ("Lidded Versus Bare Die Flip Chip Package: Impact on Thermal Performance", "Electronics Cooling magazine", "2012-06", "secondary"),
    # products
    "huawei_hc31_davinci_slides": ("DaVinci: A Scalable Architecture for Neural Network Computing (Heng Liao, Hot Chips 31)", "Huawei / Hot Chips", "2019-08", "primary"),
    "sth_ascend910_hc31": ("Huawei Ascend 910 Provides a NVIDIA AI Training Alternative", "ServeTheHome", "2019-08", "secondary"),
    "nvidia_h100_whitepaper_v102": ("NVIDIA H100 Tensor Core GPU Architecture whitepaper v1.02 (NVIDIA document; third-party mirror)", "NVIDIA", "2022", "primary"),
    "nvidia_h100_datasheet": ("NVIDIA H100 Tensor Core GPU datasheet (NVIDIA document; third-party mirror)", "NVIDIA", "2023", "primary"),
    "nvidia_blackwell_arch_page": ("NVIDIA Blackwell Architecture (technology page)", "NVIDIA", "accessed 2026-10-31", "primary"),
    "nvidia_blackwell_ultra_blog": ("Inside NVIDIA Blackwell Ultra: The Chip Powering the AI Factory Era", "NVIDIA Technical Blog", "2025", "primary"),
    "nvidia_blackwell_pr_2024": ("NVIDIA Blackwell Platform Arrives to Power a New Era of Computing", "NVIDIA Newsroom", "2024-03-18", "primary"),
    "amd_cdna3_whitepaper": ("AMD CDNA 3 Architecture white paper", "AMD", "2024-2025", "primary"),
    "amd_hc2024_mi300x": ("AMD Instinct MI300X Generative AI Accelerator and Platform Architecture (A. Smith, Hot Chips 2024)", "AMD / Hot Chips", "2024-08", "primary"),
}

F = []  # (fact_id, lane, topic, claim, value, unit, quote, file, confidence, capture, notes, render)


def f(fid, topic, claim, value, unit, quote, file, conf="high", capture="curl", notes="", render=None):
    F.append(dict(fact_id=fid, topic=topic, claim=claim, value=value, unit=unit, quote=quote, file=file,
                  confidence=conf, capture_method=capture, notes=notes, render=render))


# ---------------- HBM and interfaces ----------------
f("hbm-001", "HBM3 bandwidth", "HBM3 per-pin rate up to 6.4 Gb/s, 819 GB/s per stack", "6.4; 819", "Gb/s; GB/s",
  "defining data rates of up to 6.4 Gb/s, equivalent to 819 GB/s per device", "hbm/jedec_hbm3_pr_2022.txt")
f("hbm-002", "HBM3 channels", "HBM3 has 16 independent channels, 2 pseudo-channels each", "16 (32 pseudo)", "channels",
  "Doubling the number of independent channels from 8 (HBM2) to 16; with two pseudo channels per channel, HBM3 virtually supports 32 channels", "hbm/jedec_hbm3_pr_2022.txt")
f("hbm-003", "HBM3 stack height", "HBM3 supports 4/8/12-high TSV stacks with provision for 16-high", "4, 8, 12 (16)", "dies",
  "Supporting 4-high, 8-high and 12-high TSV stacks with provision for a future extension to a 16-high TSV stack", "hbm/jedec_hbm3_pr_2022.txt")
f("hbm-004", "HBM3 capacity", "HBM3 device densities 4 GB to 64 GB", "4-64", "GB",
  "spanning device densities from 4GB (8Gb 4-high) to 64GB (32Gb 16-high)", "hbm/jedec_hbm3_pr_2022.txt")
f("hbm-005", "HBM4 bandwidth", "HBM4: up to 8 Gb/s on a 2048-bit interface, up to 2 TB/s per stack", "8; 2048; 2", "Gb/s; bits; TB/s",
  "With transfer speeds up to 8 Gb/s across a 2048-bit interface, HBM4 boosts total bandwidth up to 2 TB/s.", "hbm/jedec_hbm4_pr_2025.txt")
f("hbm-006", "HBM4 channels", "HBM4 has 32 channels with 2 pseudo-channels each", "32", "channels",
  "from 16 channels (HBM3) to 32 channels with 2 pseudo-channels per channel", "hbm/jedec_hbm4_pr_2025.txt")
f("hbm-007", "HBM4 stack/capacity", "HBM4 supports 4/8/12/16-high stacks, 24 or 32 Gb dies, up to 64 GB", "4-16 high; 64 GB", "",
  "HBM4 supports 4-high, 8-high, 12-high and 16-high DRAM stack configurations with 24 Gb or 32 Gb die densities, providing for a higher cube density of 64GB (32 Gb 16-High).", "hbm/jedec_hbm4_pr_2025.txt")
f("hbm-008", "HBM4 supply", "HBM4 VDDQ 0.7-0.9 V, VDDC 1.0-1.05 V", "0.7-0.9; 1.0-1.05", "V",
  "JESD270-4 supports vendor specific VDDQ (0.7V, 0.75V, 0.8V or 0.9V) and VDDC (1.0V or 1.05V) levels", "hbm/jedec_hbm4_pr_2025.txt")
f("hbm-009", "HBM4 package height", "JEDEC reportedly relaxed nominal HBM4 package thickness to 775 um for 12- and 16-high", "775", "um",
  "with JEDEC confirming a relaxed nominal package thickness of 775 micrometers for both 12-high and 16-high stacked HBM4", "hbm/trendforce_hbm4_775um_2025.txt",
  conf="medium", notes="Secondary (TrendForce citing ZDNet); JEDEC standard text itself not accessed.")
f("hbm-010", "HBM3E 12-high thinning", "SK hynix 12-high 36 GB HBM3E keeps 8-high thickness; each DRAM die 40% thinner", "40% thinner; 36 GB", "",
  "SK hynix has increased the capacity by 50% by stacking 12 layers of 3GB DRAM chips at the same thickness as the previous eight-layer product. To achieve this, the company made each DRAM chip 40% thinner than before", "hbm/skhynix_hbm3e_12h_2024.txt")
f("hbm-011", "HBM3E speed", "SK hynix 12-high HBM3E runs at 9.6 Gbps", "9.6", "Gb/s per pin",
  "SK hynix has increased the speed of memory operations to 9.6 Gbps", "hbm/skhynix_hbm3e_12h_2024.txt")
f("hbm-012", "MR-MUF thermal", "Advanced MR-MUF gives 10% higher heat dissipation than previous generation (vendor claim)", "10", "%",
  "This allows to provide 10% higher heat dissipation performance compared to the previous generation", "hbm/skhynix_hbm3e_12h_2024.txt",
  notes="Vendor claim; baseline is SK hynix's previous generation, not a competitor.")
f("hbm-013", "MR-MUF definition", "MR-MUF injects liquid protective material between stacked chips and hardens it", "", "",
  "The process of stacking semiconductor chips, injecting liquid protective materials between them to protect the circuit between chips, and hardening them.", "hbm/skhynix_hbm3e_12h_2024.txt")
f("hbm-014", "HBM3E 12H bandwidth", "Samsung HBM3E 12H: up to 1,280 GB/s and 36 GB", "1280; 36", "GB/s; GB",
  "Samsung's HBM3E 12H provides an all-time high bandwidth of up to 1,280 gigabytes per second (GB/s) and an industry-leading capacity of 36 gigabytes (GB).", "hbm/samsung_hbm3e_12h_2024.txt")
f("hbm-015", "TC-NCF gap", "Samsung TC-NCF achieves a 7 um gap between stacked chips", "7", "um",
  "achieved the industry's smallest gap between chips at seven micrometers", "hbm/samsung_hbm3e_12h_2024.txt")
f("hbm-016", "thermal bumps", "Samsung uses larger bumps where heat must be dissipated, smaller ones for signals", "", "",
  "smaller bumps are used in areas for signaling and larger ones are placed in spots that require heat dissipation", "hbm/samsung_hbm3e_12h_2024.txt")
f("hbm-017", "HBM height spec", "12-layer TC-NCF parts meet the same height specification as 8-layer parts", "", "",
  "allowing the 12-layer products to have the same height specification as 8-layer ones to meet current HBM package requirements", "hbm/samsung_hbm3e_12h_2024.txt")
f("hbm-018", "HBM3E footprint", "Micron HBM3E 8H/12H form factor 11 x 11 x 0.72 mm", "11 x 11 x 0.72", "mm",
  "11mm x 11mm x 0.72mm", "hbm/micron_hbm3e_product_brief.txt", render="hbm/renders/micron_hbm3e_brief_p2.png",
  notes="Table rows are scrambled in text extraction; the render shows the row is 'Form Factor (mm)'.")
f("hbm-019", "HBM3E speed", "Micron HBM3E >9.2 Gb/s, 24 GB 8-high, >1.2 TB/s", ">9.2; >1.2", "Gb/s; TB/s",
  "Micron HBM3E has an industry best data rate of >9.2 Gb/s and 24GB", "hbm/micron_hbm3e_product_brief.txt")
f("hbm-020", "HBM3E operating temperature", "Micron HBM3E operating temperature 0 C <= T_OPER <= +105 C", "0 to 105", "C",
  "TOPER", "hbm/micron_hbm3e_product_brief.txt", capture="render", render="hbm/renders/micron_hbm3e_brief_p2.png",
  notes="Degree signs are lost in text extraction; value read from the rendered spec table (row 'Operating Temperature').")
f("hbm-021", "HBM3E TSV count", "Micron HBM3E has 2x more TSVs than HBM3 shipping solutions", "2x", "",
  "2X more TSVs compared to current", "hbm/micron_hbm3e_product_brief.txt")
f("hbm-022", "HBM2 footprint/height", "SK hynix molded KGSD: Gen2 (HBM2) 7.75 x 11.87 mm, body height 0.72 mm; Gen1 5.48 x 7.29 mm, 0.49 mm", "7.75 x 11.87; 0.72", "mm",
  "7.75 mm x 11.87mm", "hbm/skhynix_hc28_hbm_tutorial.txt", render="hbm/renders/skhynix_hc28_p8.png",
  notes="Table columns are scrambled in text; the render shows the row mapping.")
f("hbm-023", "HBM microbump", "HBM micro-bumps: 25 um CD (as reflowed), 55 um pitch, face-centred-rectangular pattern (JEDEC MPGA)", "25; 55", "um",
  "Face Centered Rectangular (FCR) pattern", "hbm/skhynix_hc28_hbm_tutorial.txt", capture="render", render="hbm/renders/skhynix_hc28_p8.png")
f("hbm-024", "HBM thermal dummy bumps", "Thermal dummy bumps enhance HBM thermal dissipation without mechanical reliability issues", "", "",
  "Thermal dummy bumps enhance thermal dissipation", "hbm/skhynix_hc28_hbm_tutorial.txt", render="hbm/renders/skhynix_hc28_p18.png")
f("hbm-025", "HBM-host link", "HBM's 1024 IOs leave the base-die PHY region and reach the host PHY through the interposer", "1024", "IO",
  "HBM 1024 IO from base die PHY region connect to host PHY through the interposer", "hbm/skhynix_hc28_hbm_tutorial.txt")
f("hbm-026", "HBM bumps (IEDM23)", "HBM's 1024 I/Os use ~25 um micro-bumps on a 96 um staggered pitch", "25; 96", "um",
  "Total number of I/Os of HBM is 1024 and its increased number can be realized by micro-bumps with about 25um diameter and 96um staggered bump pitch", "hbm/skhynix_iedm23_hbm_packaging.raw.txt",
  notes="'Staggered pitch' (96 um) and the HC28 '55 um FCR pitch' are probably different pitch definitions of a staggered array; not reconciled by the sources.")
f("hbm-027", "HBM energy", "HBM2E ~4.3 pJ/bit; HBM3E 20% lower; HBM4 expected 60% lower than HBM2E", "4.3", "pJ/bit",
  "While the power efficiency of HBM2E is about 4.3 pJ/bit, that of HBM3E is reduced by 20% and HBM4 is expected to be reduced by 60% compared with HBM2E.", "hbm/skhynix_iedm23_hbm_packaging.raw.txt")
f("hbm-028", "MR-MUF vs TC-NCF", "MR-MUF allows more thermal bumps and higher-k filler than TC-NCF (SK hynix view)", "", "",
  "Since MR-MUF does not apply pressure during chip stacking, it can create more thermal paths than TC-NCF, which is difficult to accommodate a large number of thermal bumps to.", "hbm/skhynix_iedm23_hbm_packaging.raw.txt",
  notes="SK hynix (MR-MUF vendor) perspective; Samsung argues TC-NCF thermal benefits (hbm-016).")
f("hbm-029", "microbump pitch limit", "Micro-bump joining is challenging below ~20 um pitch", "~20", "um",
  "Micro-bump joining would be challenging to achieve fine pitch under around 20um.", "hbm/skhynix_iedm23_hbm_packaging.raw.txt")
f("hbm-030", "hybrid bonding HBM", "C2W hybrid bonding removes gap-fill material to stack more dies in limited z-height", "", "",
  "Chip to wafer hybrid bonding (C2W HB) can stack more dies in a limited", "hbm/skhynix_iedm23_hbm_packaging.raw.txt")
f("hbm-031", "HBM gap-fill k", "Gap-fill thermal conductivity between stacked dies should be as high as possible", "", "",
  "the thermal conductivity of the gap-fill material between the stacked dies should be made as high as possible", "hbm/skhynix_iedm23_hbm_packaging.raw.txt")
f("hbm-032", "HBM2 bump counts", "HBM2-era bump field: 3990 TSV micro-bumps (1728 IO, 1030 ground) at 55 um pitch over ~6.0 x 2.8 mm", "3990; 1728; 1030; 55", "bumps; um",
  "Total TSV Micro Bumps: 3990", "hbm/formfactor_swtw2016_hbm_probing.txt",
  notes="Array 6022 x 2832 um and '55 um Micro Bump Pitch' are on the same slide; micro signs are garbled in the text extraction.")
f("hbm-033", "HBM1 bumps", "HBM1: micro-bump diameter 25 um, height 35 um, pitch 55 um; body height 490 um; TSV area ~1.3%, bumps ~19.6%", "25; 35; 55", "um",
  "roughly bump ratio is TSV;1.3%, bumps; 19.6%, and dummy bumps; 5%", "hbm/imaps_hbm_underfill_tsv_study.raw.txt",
  notes="Dimension line in the same paragraph reads '490 m ... 25 m ... 35 m ... 55 m' (micro signs lost).")
f("hbm-034", "HBM 12-high TSV count", "Samsung 12-layer 3D-TSV: >60,000 TSV holes; package thickness 720 um (same as 8-layer HBM2)", "60000; 720", "TSVs; um",
  "more than 60,000 TSV holes", "hbm/samsung_12layer_3dtsv_2019.txt")
f("hbm-035", "HBM package thickness", "Samsung: 12-layer package thickness 720 um, same as 8-layer HBM2", "720", "um",
  "remains the same as current 8-layer High Bandwidth Memory-2 (HBM2) products", "hbm/samsung_12layer_3dtsv_2019.txt")
f("hbm-036", "HBM4 base die", "SK hynix to use TSMC's advanced logic process for the HBM4 base die", "", "",
  "plans to adopt TSMC's advanced logic process for HBM4's base die", "hbm/skhynix_tsmc_hbm4_mou_2024.txt")
f("hbm-037", "HBM footprint (secondary)", "HBM3/3E/4 share ~10.5 x 12.0 mm footprint; HBM4 16-Hi up to ~950 um vs ~750 um 12-Hi HBM3 (press)", "10.5 x 12.0; 750-950", "mm; um",
  "HBM3/HBM3E and HBM4 share the same ~10.5 × 12.0 mm footprint", "hbm/tomshw_skhynix_hbm4_16hi.txt", conf="low",
  notes="Secondary press figures; conflict with Micron 11 x 11 mm (hbm-018) and with the reported 775 um JEDEC limit (hbm-009).")
f("hbm-038", "HBM3 PHY", "Synopsys HBM3 PHY: 2.5D JEDEC HBM3 up to 9600 Mbps; 1024-bit PHY, up to 32 pseudo-channels", "9600", "Mb/s",
  "Supports 2.5D-based JEDEC standard HBM3 DRAMs with data rates up to 9600 Mbps", "hbm/synopsys_hbm3_phy_page.txt")
f("hbm-039", "HBM3E controller", "Rambus HBM3E: 16 channels x 64 bits = 1024 bits, up to 9.6 Gb/s/pin", "1024; 9.6", "bits; Gb/s",
  "The interface features 16 independent channels, each containing 64 bits for a total data width of 1024 bits.", "hbm/rambus_hbm3e_controller_page.txt")
f("hbm-040", "HBM PHY interposer", "Cadence HBM3 PHY designed for optimized interposer routing (2.5D)", "", "",
  "Designed for optimized interposer routing", "hbm/cadence_hbm3_phy_page.txt")
f("hbm-041", "UCIe advanced/standard", "UCIe advanced package 25-55 um bump pitch, up to 2 mm and 32 Gb/s; standard package 100-130 um", "25-55; 100-130; 2; 32", "um; um; mm; Gb/s",
  "Advanced Package (25-55um bump pitch): � Up to 2mm and 32Gb/s", "hbm/ucie_hc2023_electrical.raw.txt", conf="high",
  notes="The bullet glyph is kept as the replacement character in the quote.")
f("hbm-042", "UCIe module width", "UCIe module width x64 (advanced) / x16 (standard)", "64; 16", "lanes",
  "x64 for advanced packaging � x16 for standard packaging", "hbm/ucie_hc2023_electrical.raw.txt")
f("hbm-043", "UCIe KPIs", "UCIe KPIs: S(2D) 100-130 um, <=25 mm, 28-224 GB/s/mm, 0.5 pJ/b; A(2.5D) 25-55 um, <=2 mm, 165-1317 GB/s/mm, 188-1350 GB/s/mm2, 0.25 pJ/b; 3D <=10 um, 4,000-300,000 GB/s/mm2, <0.05 pJ/b at 9 um", "see claim", "",
  "Characteristics / KPIs", "hbm/ucie_buss25_dassharma.raw.txt", capture="render", render="hbm/renders/ucie_buss25_p7.png",
  notes="Table read from the rendered slide; text extraction scrambles the cells.")
f("hbm-044", "UCIe data rates", "UCIe data rates 4, 8, 12, 16, 24, 32 GT/s", "4-32", "GT/s",
  "4, 8, 12, 16, 24, 32", "hbm/ucie_buss25_dassharma.raw.txt")
f("hbm-045", "HBM junction limits (app note)", "Broadcom HBM app note: example power-down at 95 C HBM junction; stop traffic at 90 C, restore at 85 C", "85; 90; 95", "C",
  "The power-down process is initiated when the HBM junction temperature reaches 95", "hbm/broadcom_stratadnx_hbm_appnote.txt",
  conf="medium", notes="Example configuration values for an HBM2-era networking device; not a JEDEC limit.")

# ---------------- packaging ----------------
f("pkg-001", "CoWoS-S size", "CoWoS-S interposer up to 3.3x reticle (~2700 mm2)", "3.3x; ~2700", "reticle; mm2",
  "CoWoS®-S can accommodate an interposer up to 3.3X-reticle size (or ~2700mm2).", "packaging/tsmc_cowos_page.txt")
f("pkg-002", "CoWoS-S eDTC", "CoWoS-S silicon interposer carries embedded deep trench capacitors; in production since 2012", "", "",
  "embedded deep trench capacitors over a large silicon interposer area", "packaging/tsmc_cowos_page.txt")
f("pkg-003", "CoWoS-R RDL", "CoWoS-R RDL interposer of polymer and copper traces; min 4 um pitch (2 um L/S)", "2/2; 4", "um",
  "An RDL interposer for routing, with a minimum 4μm pitch (i.e., 2μm line width/spacing).", "packaging/tsmc_cowos_page.txt")
f("pkg-004", "CoWoS-R composition", "RDL interposer is polymer and copper traces, relatively flexible", "", "",
  "An RDL interposer is comprised of polymer and copper traces and is relatively flexible.", "packaging/tsmc_cowos_page.txt")
f("pkg-005", "CTE buffer", "RDL and C4/underfill layers buffer the SoC-substrate CTE mismatch", "", "",
  "RDL layer and C4/underfill (UF) layers provide an excellent buffer", "packaging/tsmc_cowos_page.txt")
f("pkg-006", "CoWoS-L", "CoWoS-L combines RDL interposer, local silicon interconnect (LSI) bridges and eDTC", "", "",
  "combining Chip on Wafer on Substrate with RDL-based interposer, higher density embedded local silicon interconnect (LSI), eDTC, and the integration of diverse embedded chips", "packaging/tsmc_cowos_page.txt")
f("pkg-007", "CoWoS-L size", "First CoWoS-L at 3.5x reticle in volume production since 2024", "3.5x", "reticle",
  "TSMC's first CoWoS®-L at 3.5X-reticle size has been in volume production since 2024.", "packaging/tsmc_cowos_page.txt")
f("pkg-008", "LSI bridge", "LSI chips route die-to-die through multiple layers of sub-micron copper lines; pitches align with CoWoS-S", "<1", "um",
  "LSI chips for a high routing density die-to-die interconnect through multiple layers of sub-micron copper lines.", "packaging/tsmc_cowos_page.txt")
f("pkg-009", "eDTC under SoC", "CoWoS-L can integrate stand-alone eDTCs underneath the SoC die", "", "",
  "stand-alone eDTCs underneath the SoC die to improve power management", "packaging/tsmc_cowos_page.txt")
f("pkg-010", "SoIC pitch", "TSMC SoIC bond pitch starts from the sub-10 um rule", "<10", "um",
  "The bond pitch starts from the sub-10µm rule.", "packaging/tsmc_soic_page.txt")
f("pkg-011", "SoIC roadmap", "TSMC SoIC bond-pitch roadmap 9 um -> 6 um -> 3 um -> 0.9 um", "9; 6; 3; 0.9", "um",
  "Inter-chip Interconnect Scaling Roadmap", "packaging/tsmc_hotchips33_packaging_tutorial.txt", capture="render", render="packaging/renders/tsmc_hc33_p30.png")
f("pkg-012", "CoWoS-S evolution", "CoWoS-S: Cu C4 bumps; later eDTC Gen-1, thick Cu interconnect, new TSV, new TIM (lid package)", "", "",
  "New TIM (Lid package)", "packaging/tsmc_hotchips33_packaging_tutorial.txt", render="packaging/renders/tsmc_hc33_p22.png")
f("pkg-013", "CoWoS-S C4", "CoWoS-S uses Cu C4 bumps", "", "",
  "Cu C4 bumps", "packaging/tsmc_hotchips33_packaging_tutorial.txt", render="packaging/renders/tsmc_hc33_p22.png")
f("pkg-014", "CoWoS-S 2021", "3-reticle Si interposer with thicker metal (5Mi), eDTC and HBM2E qualified 2021", "3x; 5", "reticle; thick metal layers",
  "Qualify 3-reticle Si interposer with thicker metal (5Mi), eDTC* and HBM2E in", "packaging/tsmc_hotchips33_packaging_tutorial.txt")
f("pkg-015", "interposer as stress buffer", "Si interposer acts as a stress buffer between SoC and substrate (reduced chip-package interaction)", "", "",
  "Si interposer, a stress buffer between SoC and substrate, for reduced CPI", "packaging/tsmc_hotchips33_packaging_tutorial.txt")
f("pkg-016", "InFO RDL / substrate", "InFO_oS: min 2/2 um, 5 RDL layers, 130 um pitch Cu bump; 2.5x reticle on 110 mm square substrate (2021)", "2/2; 5; 130; 110", "um; layers; um; mm",
  "Offers Min. 2/2 m 5x RDL layers with 130m pitch Cu bump.", "packaging/tsmc_hotchips33_packaging_tutorial.txt",
  notes="Micro signs dropped by text extraction ('2/2 m' = 2/2 um, '130m' = 130 um).")
f("pkg-017", "large substrate", "2.5x reticle InFO_oS on a 110 mm square substrate in 2021", "110", "mm",
  "substrate 110mmSQ", "packaging/tsmc_hotchips33_packaging_tutorial.txt")
f("pkg-018", "Xilinx SSIT stack", "Virtex-7 SSIT: interposer M1-M4 2 um pitch; TSV >10 um diameter, 210 um pitch; micro-bump 45 um pitch; C4 210 um pitch; substrate 4-2-4, 1.0 mm BGA pitch; 10K-30K chip-to-chip connections", "see claim", "",
  "4-2-4 Layer, 1.0 mm", "packaging/xilinx_cpmt1104b.txt", capture="render", render="packaging/renders/xilinx_cpmt1104b_p15.png",
  notes="Table cells are scrambled in text extraction; values read from the render (courtesy Xilinx, TSMC, Amkor).")
f("pkg-019", "Xilinx interposer metal", "65 nm passive interposer with four layers of metallization", "4", "metal layers",
  "built on a low-risk, high-yield 65 nm process and provides four layers of metallization", "packaging/xilinx_wp380.txt")
f("pkg-020", "die-to-die count", "Silicon interposer enables >10,000 die-to-die connections (~20x denser wire pitch than organic)", ">10000", "connections",
  "that enables more than 10,000 die-to-die connections", "packaging/xilinx_wp380.txt")
f("pkg-021", "Xilinx test vehicle", "Interposer test chip: micro-bumps at 45 um pitch; interposer 100 um thick; 42.5 mm substrate; C4 at 180 um pitch", "45; 100; 42.5; 180", "um; um; mm; um",
  "A representative silicon interposer test chip with thousands of micro-bumps at 45um pitch has been fabricated. The silicon interposer is 100um thick, and is mounted on a 42.5mmx42.5mm substrate through 180um pitch C4 bumps.", "thermal/imaps_xilinx_thermal_tsv_interposer.raw.txt")
f("pkg-022", "FCBGA envelope", "Amkor FCBGA: package 10-67.5 mm (85 mm in qual); 0.4-1.0 mm BGA pitch; 90 um min array bump pitch; 4-18 layer build-up", "see claim", "",
  "Package sizes from 10 mm to 67.5 mm", "packaging/amkor_fcbga_ds831.txt")
f("pkg-023", "FCBGA build-up", "Amkor FCBGA substrates: 4-18 layer laminate build-up; coreless option", "4-18", "layers",
  "4-18 layer laminate build up", "packaging/amkor_fcbga_ds831.txt")
f("pkg-024", "FCBGA formats", "FCBGA formats: bare die, lidded, stiffener ring", "", "",
  "Stiffener ring", "packaging/amkor_fcbga_ds831.txt", notes="Format list in the data sheet: Bare die / Lidded / Stiffener ring (column text interleaved in extraction).")
f("pkg-025", "lidded for high performance", "High-performance ASICs typically use a lidded format with controlled bondline die attach to a copper heat spreader", "", "",
  "High-performance ASIC products typically utilize a lidded format that features a controlled bondline die attach direct to a copper heat spreader.", "packaging/amkor_fcbga_ds831.txt")
f("pkg-026", "secondary path in FCBGA", "Bare/molded FCBGA: bumps and core vias give a path from die active side through substrate to the board", "", "",
  "provides a lower resistance path from the active side of the die through the substrate", "packaging/amkor_fcbga_ds831.txt")
f("pkg-027", "BGA ball count", "Amkor full-array ball count: 55 mm body at 1 mm pitch = 3136 balls", "3136", "balls",
  "55 3136", "packaging/amkor_fcbga_ds831.txt", conf="medium",
  notes="Table columns partially scrambled; 3136 = 56 x 56, consistent with a 55 mm body at 1.0 mm pitch.")
f("pkg-028", "C4 bump geometry", "Standard flip-chip bump 60-100 um high, 80-125 um diameter; Cu pillar ~40 um high capped with SnAg", "60-100; 80-125; 40", "um",
  "60-100", "packaging/amkor_flipchip_ts102.txt",
  notes="Full text: 'bump is typically 60-100 um high and 80-125 um in diameter, while a copper pillar (CuP) bump is typically a 40 um high Cu pillar capped with SnAg' (micro signs garbled).")
f("pkg-029", "Cu pillar", "Cu pillar bump capped with SnAg", "40", "um",
  "bump is typically a 40", "packaging/amkor_flipchip_ts102.txt")
f("pkg-030", "underfill role", "Underfill is an engineered epoxy filling die-to-carrier gap, reducing solder-joint stress from CTE mismatch", "", "",
  "Underfill is a specially engineered epoxy that fills the area between the die", "packaging/amkor_flipchip_ts102.txt")
f("pkg-031", "substrate roadmap", "Kyocera: large body 90 mm SQ with 10 build-up layers per side; L/S 9/12 um", "90; 10/side; 9/12", "mm; layers; um",
  "Large body and high layer count", "packaging/kyocera_fcbga_organic_substrates.txt")
f("pkg-032", "substrate core thickness", "Conventional FCBGA core thickness 400-1,600 um; thin core 150/200/250 um", "400-1600; 150-250", "um",
  "thickness: 400 - 1,600", "packaging/kyocera_fcbga_organic_substrates.txt")
f("pkg-033", "substrate max size", "Kyocera max body size roadmap up to 120 x 120 mm and 130 x 130 mm; build-up up to 14/x/14", "120-130; 14/x/14", "mm; layers",
  "120 x 120 mm", "packaging/kyocera_fcbga_organic_substrates.txt")
f("pkg-034", "substrate bump pitch", "Kyocera substrate bump pitch / SRO 130/60 um to 110/55 um (90/50 um roadmap)", "130-90", "um",
  "Bump pitch / SRO", "packaging/kyocera_fcbga_organic_substrates.txt")
f("pkg-035", "EMIB", "EMIB connects chiplets without a silicon interposer; 2nd-gen bump pitch 55 -> 45 um", "55; 45", "um",
  "pitch from 55 to 45 microns", "packaging/intel_qr_vol6_adv_packaging.txt")
f("pkg-036", "EMIB no interposer", "EMIB enables high-bandwidth chiplet connectivity without a silicon interposer", "", "",
  "EMIB enables high bandwidth connectivity between multiple large chiplets without the use of a silicon", "packaging/intel_qr_vol6_adv_packaging.txt")
f("pkg-037", "Foveros Direct", "Foveros Direct 3D first generation uses Cu bonding at 9 um pitch", "9", "um",
  "generation of Foveros Direct 3D uses copper bonding at a pitch of 9um", "packaging/intel_qr_vol6_adv_packaging.txt")
f("pkg-038", "CoWoS molding", "In a CoWoS flow, dies on the interposer wafer are underfilled then encapsulated in molding compound or molding underfill", "", "",
  "Encapsulant 46 may be a molding compound, a molding underfill, or the like.", "packaging/tsmc_patent_us20200381391_cowos.txt")
f("pkg-039", "lidless", "Lidless package lets the heat sink contact the die directly; flatness worsens with package size; stiffener keeps it flat", "", "",
  "allows a heat sink to directly contact the die, which allows for better thermal performance than electronic packages that include a lid.", "packaging/google_patent_us10083920_stiffener.txt")
f("pkg-040", "lidless flatness", "Lidless designs suffer increasing flatness problems as packages grow", "", "",
  "suffer from increasing flatness problems as the packages grow in size", "packaging/google_patent_us10083920_stiffener.txt")
f("pkg-041", "core rail", "GenAI processor core VDD as low as 0.7 V, +/-5% tolerance, dI/dt >= 2000 A/us", "0.7; 2000", "V; A/us",
  "including the main rail (core VDD) as low as 0.7 volts", "packaging/vicor_vpd_genai_article.txt", conf="medium", notes="VR vendor article (Vicor).")
f("pkg-042", "HBM rail", "HBM VDD 1.1 or 1.2 V nominal (own domain)", "1.1-1.2", "V",
  "The HBMs in the processor array have their own voltage domain (HBM VDD) at 1.1V or 1.2V nominal", "packaging/vicor_vpd_genai_article.txt", conf="medium")
f("pkg-043", "bypass capacitance", "A 1000 A TDC processor needs >=3 mF bypass capacitance, filling the PCB area beneath the processor", "1000; 3", "A; mF",
  "a 1000A Thermal Design Current (TDC or continuous draw) genAI training processor requires a large amount of bypass capacitance, 3mF or more", "packaging/vicor_vpd_genai_article.txt", conf="medium")
f("pkg-044", "lateral VR", "30+ VR phases arranged laterally around the processor; >=50 W I2R loss in board planes", "30; 50", "phases; W",
  "Today's solutions use thirty or more voltage regulator (VR) modulated phases arranged laterally around the genAI training processor", "packaging/vicor_vpd_genai_article.txt", conf="medium")
f("pkg-045", "vertical power delivery", "Moving one PoL module under the processor cut PDN impedance 60 -> 11 uOhm; ~3500 mm2 package footprint", "60; 11; 3500", "uOhm; uOhm; mm2",
  "The parallel lumped PDN impedance dropped from 60 to 11", "packaging/vicor_vpd_genai_article.txt", conf="medium")
f("pkg-046", "eDTC density", "TSMC iCap deep-trench capacitor in Si interposer: up to 340 nF/mm2, 40 x 40 um standard cell (~20x planar MIM)", "340", "nF/mm2",
  "they said the capacitance density it can achieve is up to 340 nF/mm²", "packaging/mediaupdate_iedm2019_part2.txt", conf="medium",
  notes="Secondary blog report of TSMC IEDM 2019 paper (Hou et al.); IEEE Xplore page not machine-readable.")
f("pkg-047", "substrate roadmap (press)", "Ibiden roadmap: 90 x 90 mm (2026), 110 x 110 mm (2028); 10-X-10 build-up (2026) to 14-X-14 (2030)", "90-130; 10-14/side", "mm; layers",
  "Ibiden's roadmap targets a 10-X-10 buildup structure in 2026", "packaging/tomshw_abf_substrates_2026.txt", conf="medium")
f("pkg-048", "substrate structure (press)", "AI ABF substrates: rigid glass-reinforced resin core between build-up layers of Cu and insulating film", "", "",
  "ABF substrates used in AI accelerators typically consist of a rigid, glass-reinforced resin core sandwiched between successive build-up layers of copper wiring and insulating film.", "packaging/tomshw_abf_substrates_2026.txt", conf="medium")
f("pkg-049", "BGA ball (example)", "FCBGA example (1.00 mm pitch): ball diameter 0.40/0.50/0.60 mm; ball height 0.31-0.41 mm", "0.5 (0.4-0.6)", "mm",
  "Ball Diameter", "packaging/microchip_fcbga196_c04_25015.txt", capture="render", render="packaging/renders/microchip_fcbga196_p2.png", conf="medium",
  notes="Small 15 mm FCBGA; representative of 1.0 mm pitch ball geometry only.")
f("pkg-050", "BGA ball / lid (example)", "Flat-lid FCBGA 29 mm, 1.00 mm pitch: ball diameter 0.600 nominal; stand-off 0.40-0.60 mm; total thickness 2.552-3.052 mm", "0.6; 0.4-0.6; 2.55-3.05", "mm",
  "", "packaging/renesas_alg784_fcbga_29mm.txt", capture="render", render="packaging/renders/renesas_alg784_p1.png", conf="medium",
  notes="Vector drawing; no extractable text. Networking-class FCBGA, not an AI accelerator.")
f("pkg-051", "TIM resistance (TSMC)", "TSMC cooling benchmark (area-specific TR, C*mm2/W): liquid-metal TIM 4, fusion-bonded oxide TIM 1.5, bulk Si 5 (2 thinned), Si-in-lid 2, Si/water 11-20", "4; 1.5; 5; 11-20", "C*mm2/W",
  "TIM 4 4 1.5 1.5", "packaging/tsmc_hotchips33_packaging_tutorial.txt", render="packaging/renders/tsmc_hc33_p36.png",
  notes="Units (C*mm2/W) visible only in the render; integrated Si micro-cooler test structures, not a production lid.")
f("pkg-052", "total TR (TSMC)", "TSMC cooling benchmark total TR 13-31 C*mm2/W depending on scheme and flow", "13-31", "C*mm2/W",
  "Total TR 31 22 28.5 19.5 22 13", "packaging/tsmc_hotchips33_packaging_tutorial.txt", render="packaging/renders/tsmc_hc33_p36.png")

# ---------------- thermal ----------------
f("thm-001", "TAP-2.5D layers", "TAP-2.5D stacks six modeling layers: substrate, C4, interposer, microbump, chiplet, TIM", "6", "layers",
  "From the bottom up, as illustrated in Fig. 1, the layers are organic substrate, C4 bump layer, silicon interposer, microbump layer, chiplet layer, and Thermal Interface Material (TIM).", "thermal/tap25d_date2021.raw.txt")
f("thm-002", "TAP-2.5D package", "TAP-2.5D: ambient 45 C, 64x64 grid, spreader 2x interposer edge, heatsink 2x spreader edge, convective resistance adjusted", "45; 64; 2x; 2x", "C; grid; ; ",
  "we set the ambient temperature to 45oC, the grid model resolution to 64", "thermal/tap25d_date2021.raw.txt")
f("thm-003", "TAP-2.5D convection", "TAP-2.5D adjusts convective resistance to keep heat transfer coefficient constant", "", "",
  "To keep the heat transfer coefficient consistent across all simulations, we adjust the convective resistance of the heatsink.", "thermal/tap25d_date2021.raw.txt")
f("thm-004", "TAP-2.5D properties origin", "TAP-2.5D layer properties taken from real systems [28],[29] (Xilinx 28nm FPGA on 65nm interposer; CEA-Leti interposer)", "", "",
  "Our 2.5D system model uses the properties (such as layer thickness, materials, dimensions of bumps, and TSVs) of real systems [28], [29].", "thermal/tap25d_date2021.raw.txt")
f("thm-005", "TAP-2.5D underfill", "Epoxy resin underfills spacing between C4 bumps, microbumps and chiplets; substrate drawn as organic FR-4", "", "",
  "Epoxy resin is often used to underfill the spacing between C4 bumps, between microbumps, and between chiplets.", "thermal/tap25d_date2021.raw.txt")
f("thm-006", "TAP-2.5D interposer", "TAP-2.5D evaluation uses 45 mm x 45 mm interposers", "45", "mm",
  "Our evaluation uses 45mm", "thermal/tap25d_date2021.raw.txt")
f("thm-007", "TAP-2.5D Ascend dims", "TAP-2.5D Table II Ascend 910: Virtuvian 31.4 x 14.5 mm 256 W; Nimbus 10.5 x 16 mm 14 W; HBM 7.75 x 11.87 mm 20 W", "see claim", "mm; W",
  "Widths [mm] 12 18.2 7.75 8.25 8.75 31.4 10.5 7.75", "thermal/tap25d_date2021.txt",
  notes="Heights row: 12 18.2 11.87 9 8.75 14.5 16 11.87; Power row: 105 295 20 150 20 256 14 20.")
f("thm-008", "TAP-2.5D threshold", "TAP-2.5D uses 85 C as the typical acceptable threshold", "85", "C",
  "threshold of 85oC", "thermal/tap25d_date2021.raw.txt")
f("thm-009", "HotSpot TIM2", "HotSpot does not directly support TIM2 between spreader and heat sink", "", "",
  "We note that the thermal interface material between the heat spreader and heat sink (TIM2) is not directly supported by HotSpot; hence, we had to ignore it in this work.", "thermal/hotspot60_tr_https.raw.txt")
f("thm-010", "HotSpot lateral", "HotSpot validation: it underestimates lateral heat transfer", "", "",
  "This phenomenon indicates that HotSpot is underestimating the amount of heat transferred laterally.", "thermal/hotspot60_tr_https.raw.txt")
f("thm-011", "HotSpot detailed 3D", "HotSpot 6.0 detailed-3D allows per-block heterogeneous properties in grid mode with .lcf", "", "",
  "We note that currently, heterogeneous layers could only be modeled in grid-mode with .lcf file specified.", "thermal/hotspot60_tr_https.raw.txt")
f("thm-012", "HotSpot secondary path", "Secondary path = silicon -> interconnect -> C4 -> package substrate -> solder balls -> PCB", "", "",
  "The secondary heat transfer path refers to the heat escape path from the silicon to on-chip interconnect layers, C4 pads, packaging substrate, solder balls and printed-circuit board.", "thermal/hotspot60_tr_https.raw.txt")
f("thm-013", "material k (Xilinx)", "Room-temp k: organic core 0.8, prepreg 0.35, Si 117.5, Cu 389, solder mask 0.24, TIM1 0.92 W/mK", "0.8; 0.35; 117.5; 389; 0.24; 0.92", "W/mK",
  "Copper 389", "thermal/imaps_xilinx_thermal_tsv_interposer.txt",
  notes="Other rows in the same table: 'Organic core 0.8', 'Prepeg 0.35', 'Si 117.5', 'Solder mask 0.24', 'TIM1 0.92'.")
f("thm-014", "material k (Xilinx) prepreg", "Prepreg (build-up dielectric) k 0.35 W/mK", "0.35", "W/mK", "Prepeg 0.35", "thermal/imaps_xilinx_thermal_tsv_interposer.txt")
f("thm-015", "material k (Xilinx) core", "Organic core k 0.8 W/mK", "0.8", "W/mK", "Organic core 0.8", "thermal/imaps_xilinx_thermal_tsv_interposer.txt")
f("thm-016", "material k (Xilinx) Si", "Silicon k 117.5 W/mK (room temperature, as used in Xilinx model)", "117.5", "W/mK", "Si 117.5", "thermal/imaps_xilinx_thermal_tsv_interposer.txt")
f("thm-017", "Si k(T)", "Silicon k ~ 1.5 (T/300)^-4/3 W/cmK; literature values vary 68.8-157 W/mK; highly doped Si ~80% of pure", "150 at 300 K", "W/mK",
  "k = 1.5 (T/300)-4/3", "thermal/ecool_si_thermal_conductivity_1998.txt", conf="medium",
  notes="Formula in W/(cm*K): 150 W/mK at 300 K, ~119 at 358 K, ~112 at 373 K (computed by lane1).")
f("thm-018", "Si k (doped)", "Highly doped silicon k ~ 80% of pure value", "0.8x", "",
  "thermal conductivity of highly doped Silicon can be calculated at: 80% of the", "thermal/ecool_si_thermal_conductivity_1998.txt", conf="medium")
f("thm-019", "Si k (ioffe)", "Silicon thermal conductivity 1.3 W/(cm C) (NSM archive)", "130", "W/mK",
  "1.3 W cm-1°C-1", "thermal/ioffe_si_thermal_http.txt", conf="medium", notes="Retrieved over plain HTTP after a TLS chain error on HTTPS.")
f("thm-020", "indium k", "Indium bulk thermal conductivity 86 W/mK", "86", "W/mK",
  "Indium's high bulk thermal conductivity (86 W/mK)", "thermal/indium_tim_products_page.txt")
f("thm-021", "PTM7950", "PTM7950 PCM TIM: 8.5 W/mK, <0.04 C*cm2/W (no shim), min BLT ~20 um, typical <50 um", "8.5; 0.04; 20-50", "W/mK; C*cm2/W; um",
  "Min BLT~20um, typical BLT is", "thermal/solstice_ptm7950_tds.txt", notes="Table row 'Thermal Conductivity ... 8.5' and 'Thermal Impedance ... 0.04' (degree signs garbled).")
f("thm-022", "PTM7950 k", "PTM7950 thermal conductivity 8.5 W/mK (ASTM D5470)", "8.5", "W/mK", "ASTM D5470 8.5 8.5", "thermal/solstice_ptm7950_tds.txt")
f("thm-023", "underfill k", "Henkel LOCTITE ECCOBOND UF 8807 semiconductor-level capillary underfill: 0.6 W/mK", "0.6", "W/mK",
  "0.6 W/m.K", "thermal/krayden_uf8807.txt", conf="medium", notes="Distributor page value; official Henkel TDS not retrieved.")
f("thm-024", "mold compound k", "SUMIKON EME-G700LA epoxy molding compound: 0.96 W/(m C)", "0.96", "W/mK",
  "THERMAL CONDUCTIVITY SB-U-02-004 W/m C 96x 10-2", "thermal/sumikon_g700l.txt")
f("thm-025", "SAC305 k", "SAC305 solder thermal conductivity 58 W/mK", "58", "W/mK",
  "Thermal conductivity 58 W/m/K", "thermal/solderconnection_sac305.txt", conf="medium")
f("thm-026", "coupling via spreader", "Majority of inter-chiplet heat transfer occurs through the heat spreader, not the interposer (limits thermal floorplanning)", "", "",
  "the majority of inter-chiplet heat transfer occurs through the high thermal conductivity heat spreader rather than the interposer", "thermal/ucla_embedded_isolators_2p5d.raw.txt", conf="medium",
  notes="One study (ANSYS Icepak, V100-like GPU+HBM and a TAP-2.5D-based HI system). Directly relevant to SentiLab's floorplanning premise.")
f("thm-027", "HBM refresh", "HBM refresh rate doubles above manufacturer trip points (reported 75-95 C); up to 4x nominal", "75-95; 4x", "C",
  "Previous works have reported that these trip temperatures lie between 75-95 degrees", "thermal/ucla_embedded_isolators_2p5d.raw.txt", conf="medium")
f("thm-028", "TIM k (paper)", "A conventional high-performance TIM is around 20 W/mK", "20", "W/mK",
  "A conventional high performance TIM is around 20 W/mK", "thermal/ucla_embedded_isolators_2p5d.raw.txt", conf="medium")
f("thm-029", "Purdue model stack", "Published 2.5D FEM stack: logic Si 26x26 mm x 710 um + 10 um BEOL; HBM base 12x7.75 mm x 50 um; DRAM 11.5x7.5 mm x 35 um (top 66 um); 3 um BEOL; 15 um bumps; interposer 42x42 mm x 100 um + 10 um BEOL; Cu pillar 50 um; substrate 65x65 mm x 500 um", "see claim", "um",
  "Logic Si 26 26 710", "thermal/itherm2024_dual_sided_bspdn.txt",
  notes="Z column header reads 'Z(m)' with the micro sign lost; logic 710+10 = 720 um and HBM stack sums to 720 um, consistent with um.")
f("thm-030", "Purdue HBM layers", "HBM DRAM 1-11 Si 35 um; DRAM 12 Si 66 um; base (ctrl) Si 50 um", "35; 66; 50", "um",
  "HBM DRAM 1-11 Si 11.5 7.5 35", "thermal/itherm2024_dual_sided_bspdn.txt")
f("thm-031", "HBM bond R", "HBM internal resistance dominated by bond interfaces (bumps + underfill): 3.8 mm2*K/W each", "3.8", "mm2*K/W",
  "contributing an equivalent thermal resistance of 3.8", "thermal/itherm2024_dual_sided_bspdn.raw.txt", notes="Cited by the authors from their ref. [16].")
f("thm-032", "planarized package", "Logic die and HBM stacks assumed equal height (planarized); gap filled with mold", "", "",
  "An equivalent height is assumed for both the logic die and the HBM stacks, resulting in a planarized package following the assembly process.", "thermal/itherm2024_dual_sided_bspdn.raw.txt")
f("thm-033", "Purdue power", "Assumed 1500 W on 26x26 mm logic (225 W/cm2); HBM 20 W (8 W base + 12 x 1 W)", "1500; 225; 20", "W; W/cm2; W",
  "This results in a cumulative power of 20W for each of the HBM modules.", "thermal/itherm2024_dual_sided_bspdn.raw.txt", conf="medium",
  notes="Model assumptions, not product data.")
f("thm-034", "HBM base hottest", "In that model the HBM base (controller) die is the hottest layer of the stack", "", "",
  "while the controller at the HBM module's base shows the highest temperature", "thermal/itherm2024_dual_sided_bspdn.raw.txt", conf="medium")
f("thm-035", "PCB path R", "Model PCB-side equivalent thermal resistance 20 K/W", "20", "K/W",
  "an equivalent thermal resistance of 20 K/W is assumed", "thermal/itherm2024_dual_sided_bspdn.raw.txt", conf="medium")
f("thm-036", "top-side heat share", "Some 95% of a chip's heat is removed from the top of the package (imec, via IEEE Spectrum)", "95", "%",
  "Generally, some 95 percent of a chip's heat is removed from the top of the package", "thermal/ieee_spectrum_hbm_on_gpu_imec.txt", conf="medium")
f("thm-037", "2.5D baseline power", "imec 2.5D baseline: GPU 414 W plus ~40 W for four HBM stacks", "414; 40", "W",
  "the model GPU consumes 414 watts", "thermal/ieee_spectrum_hbm_on_gpu_imec.txt", conf="medium")
f("thm-038", "junction limits", "SoC Tj max typically 105 C; early HBM 85 C (single refresh) / 95 C (double); later HBM 95/105 C", "105; 85/95; 95/105", "C",
  "the SOC chiplet is typically operating with a maximum junction temperature of 105", "thermal/vertiv_coolant_temp_roadmap.txt", conf="medium")
f("thm-039", "cold plate R", "Single-phase heat sinks: 0.039 K/W at 1000 W (fluid to Tcase, dielectric coolant, Intel TTV)", "0.039", "K/W",
  "0.039 K/W at 1000 W", "thermal/iceotope_1000w_whitepaper.txt", conf="medium", notes="Vendor test; case-referenced, not junction.")
f("thm-040", "OCP R elements", "Junction-to-coolant resistance elements: coldplate, TIM2, lid & TIM1, lateral crosstalk, die stack", "", "",
  "Coldplate � TIM2 � Lid & TIM1 � Lateral heat crosstalk � Die Stack", "thermal/ocp_oai_liquid_cooling_guidelines.raw.txt")
f("thm-041", "lidded vs bare", "Exposed-die (FCmBGA) has one interface (TIM II); lidded FCLBGA has TIM I and TIM II", "", "",
  "the FCmBGA package provides the lowest thermal resistance since there is only one interface (TIM II) whereas the FCLBGA has two interfaces, TIM I and TIM II.", "thermal/ecool_lidded_vs_bare_die_2012.txt", conf="medium")

# ---------------- products ----------------
f("prd-001", "Ascend 910 dies", "Ascend 910: 8 dies; two dummy dies for mechanical uniformity", "8; 2", "dies",
  "Two dummy dies are added to ensure mechanical uniformity", "products/huawei_hc31_davinci_slides.txt", render="products/renders/huawei_hc31_p37.png")
f("prd-002", "Ascend 910 areas", "Ascend 910 silicon: 456 + 168 + 96x4 + 110x2 = 1228 mm2", "1228", "mm2",
  "456+168+96x4+110x2=1228mm2", "products/huawei_hc31_davinci_slides.txt", render="products/renders/huawei_hc31_p37.png")
f("prd-003", "Ascend 910 die areas", "Vitruvian 456 mm2, Nimbus 168 mm2, HBM 96 mm2 each, dummy 110 mm2 each", "456; 168; 96; 110", "mm2",
  "Vitruvian Nimbus 456mm2 168mm2", "products/huawei_hc31_davinci_slides.txt", render="products/renders/huawei_hc31_p37.png")
f("prd-004", "Ascend 910 spacing", "Ascend 910 floorplan: 0.72 mm gap compute-to-HBM row, 2 mm between adjacent HBMs", "0.72; 2", "mm",
  "0.72mm", "products/huawei_hc31_davinci_slides.txt", render="products/renders/huawei_hc31_p37.png",
  notes="Gap assignment read from the drawing (arrows); text alone does not bind the values to positions.")
f("prd-005", "Ascend 910 power", "Ascend 910 power 350 W", "350", "W", "Power: 350W", "products/huawei_hc31_davinci_slides.txt", render="products/renders/huawei_hc31_p33.png")
f("prd-006", "Ascend 910 HBM BW", "Ascend 910 off-chip HBM bandwidth 1.2 TB/s", "1.2", "TB/s", "HBM: 1.2 TByte/s", "products/huawei_hc31_davinci_slides.txt")
f("prd-007", "Ascend 910 process", "Ascend 910 process 7+ nm EUV", "7+", "nm",
  "Ascend 910", "products/huawei_hc31_davinci_slides.txt", capture="render", render="products/renders/huawei_hc31_p33.png")
f("prd-008", "Ascend 910 dummy (press)", "Two 110 mm2 dummy dies for mechanical stability (press)", "110", "mm2",
  "For mechanical stability, there are two 110mm2 dummy dies integrated.", "products/sth_ascend910_hc31.txt", conf="medium")
f("prd-009", "H100 die", "GH100: TSMC 4N, 80 billion transistors, 814 mm2", "814; 80e9", "mm2; transistors",
  "with 80 billion transistors, a die size of 814 mm2", "products/nvidia_h100_whitepaper_v102.txt")
f("prd-010", "H100 HBM sites", "Full GH100: 6 HBM3/HBM2e stacks, 12 x 512-bit controllers", "6", "stacks",
  "6 HBM3 or HBM2e stacks, 12 512-bit Memory Controllers", "products/nvidia_h100_whitepaper_v102.txt")
f("prd-011", "H100 SXM5 HBM", "H100 SXM5: 80 GB, 5 HBM3 stacks, 10 x 512-bit controllers", "5", "stacks",
  "80 GB HBM3, 5 HBM3 stacks, 10 512-bit Memory Controllers", "products/nvidia_h100_whitepaper_v102.txt")
f("prd-012", "H100 TDP", "TDP: A100 400 W, H100 SXM5 700 W, H100 PCIe 350 W", "700", "W",
  "TDP1 400 Watts 700 Watts 350 Watts", "products/nvidia_h100_whitepaper_v102.txt")
f("prd-013", "H100 bandwidth", "H100 SXM memory bandwidth 3.35 TB/s; max TDP up to 700 W", "3.35", "TB/s",
  "3.35TB/s", "products/nvidia_h100_datasheet.txt")
f("prd-014", "Blackwell", "Blackwell: 208B transistors, TSMC 4NP, two reticle-limited dies joined by 10 TB/s chip-to-chip link", "208e9; 2; 10", "transistors; dies; TB/s",
  "All NVIDIA Blackwell products feature two reticle-limited dies connected by a 10 terabytes per second (TB/s) chip-to-chip interconnect", "products/nvidia_blackwell_arch_page.txt")
f("prd-015", "NV-HBI", "NV-HBI die-to-die interconnect provides 10 TB/s", "10", "TB/s",
  "NVIDIA High-Bandwidth Interface (NV-HBI), a custom, power-efficient die-to-die interconnect technology that provides 10 TB/s of bandwidth", "products/nvidia_blackwell_ultra_blog.txt")
f("prd-016", "Blackwell Ultra HBM", "Blackwell Ultra: 288 GB HBM3E, 8 TB/s", "288; 8", "GB; TB/s",
  "HBM3E memory capacity reaches 288 GB with 8 TB/s bandwidth", "products/nvidia_blackwell_ultra_blog.txt")
f("prd-017", "GB200 cooling", "GB200 NVL72 is a liquid-cooled rack-scale design", "", "",
  "The GB200 NVL72 is a liquid-cooled solution", "products/nvidia_blackwell_arch_page.txt")
f("prd-018", "Blackwell package (press)", "Blackwell mounts two reticle-sized dies and eight HBM3E stacks on one package", "2; 8", "dies; stacks",
  "Nvidia's Blackwell generation mounts two reticle-sized GPU dies and eight HBM3E stacks on a single package", "packaging/tomshw_abf_substrates_2026.txt", conf="medium")
f("prd-019", "MI300 construction", "MI300: up to 8 XCDs stacked on 4 IODs with Infinity Fabric, 8 HBM stacks", "8; 4; 8", "XCD; IOD; stacks",
  "integrates up to 8 vertically stacked accelerator complex dies (XCD) and 4 I/O dies (IOD)", "products/amd_cdna3_whitepaper.txt")
f("prd-020", "MI300 IOD", "IODs on TSMC 6nm, stacked beneath a pair of XCDs", "6", "nm",
  "The IODs are manufactured on TSMC's 6nm process and vertically stacked beneath a pair of XCDs.", "products/amd_cdna3_whitepaper.txt")
f("prd-021", "MI300X memory", "MI300X: 5.2 Gbps HBM3, 24 GB per stack, 192 GB, 5.3 TB/s", "5.2; 24; 192; 5.3", "Gbps; GB; GB; TB/s",
  "the memory controllers drive a bus that operates at 5.2 Gbps and each stack contains 24GB", "products/amd_cdna3_whitepaper.txt")
f("prd-022", "MI300X power", "MI300X 750 W", "750", "W", "MI300X (750W)", "products/amd_cdna3_whitepaper.txt")
f("prd-023", "MI325X", "MI325X: 6.0 Gbps HBM3E, 32 GB/stack, 256 GB, 6.0 TB/s; 1000 W", "256; 6.0; 1000", "GB; TB/s; W",
  "each stack contains 32GB of memory with a total of 256GB HBM3E memory", "products/amd_cdna3_whitepaper.txt")
f("prd-024", "MI300X transistors", "MI300X: 153 billion transistors in TSMC 5nm | 6nm", "153e9", "transistors",
  "153 Billion Transistors in TSMC 5nm | 6nm FinFET", "products/amd_hc2024_mi300x.txt")
f("prd-025", "MI300X D2D", "MI300X XCD/IOD interface 2.1 TB/s; Infinity Fabric AP 4.8 TB/s and 6 TB/s bisection", "2.1; 4.8; 6", "TB/s",
  "4.8 TB/s bisection", "products/amd_hc2024_mi300x.txt", render="products/renders/amd_hc2024_p4.png")

# ---------------- additions ----------------
f("hbm-046", "HBM in-stack bumps", "Stacked DRAM dies use ~20 um diameter micro-bumps with underfill (HBM1)", "20", "um",
  "Also stacked DRAM dies have 20 m diameter micro-bumps and underfill material", "hbm/imaps_hbm_underfill_tsv_study.raw.txt",
  notes="Micro sign lost in extraction ('20 m' = 20 um).")
f("hbm-047", "HBM construction", "HBM is a molded known-good stacked die: 1 base die + 2/4/8 DRAM core dies, side-molded", "1 + 2/4/8", "dies",
  "mKGSD (1 Base + 2/4/8 DRAM (Core) ; molded Known Good Stacked Die)", "hbm/skhynix_hc28_hbm_tutorial.txt", render="hbm/renders/skhynix_hc28_p8.png")
f("hbm-048", "HBM2 bandwidth", "HBM2-era stack: 1024 DQ, up to 256 GB/s", "256", "GB/s",
  "Up to 256GB/s", "hbm/skhynix_hc28_hbm_tutorial.txt")
f("pkg-053", "C4 array pitch", "Flip-chip full area array pitch available down to 130 um", "130", "um",
  "Full area array pitch available to 130", "packaging/amkor_flipchip_ts102.txt")
f("thm-042", "cold plate material", "Copper is the most used cold-plate material", "", "",
  "copper is the most used material in the cold plate", "thermal/ocp_oai_liquid_cooling_guidelines.raw.txt")

f("thm-043", "heat source location", "Heat is generated in the thin active (FEOL) region of the die", "", "",
  "The heat is generated in the thin active region of the chip, marked as front-end-of-line (FEOL)", "thermal/itherm2024_dual_sided_bspdn.raw.txt")
f("thm-044", "coolants", "DI water and aqueous ethylene/propylene glycol are the most popular cold-plate coolants", "", "",
  "DI Water, aqueous ethylene glycol solution and aqueous propylene glycol solution are the most popular coolants", "thermal/ocp_oai_liquid_cooling_guidelines.raw.txt")
f("pkg-054", "bump metallurgy", "Flip-chip bumps: Pb-free 98.2Sn/1.8Ag and Cu pillar", "98.2/1.8", "wt% Sn/Ag",
  "Pb-free (98.2% Sn/1.8% Ag) and Cu pillar bumping", "packaging/amkor_flipchip_ts102.txt")
f("pkg-055", "flip-chip orientation", "Flip chip attaches the die face-down with an area array of bumps to the substrate", "", "",
  "Flip chip interconnect utilizes array interconnect of die to substrate as", "packaging/amkor_fcbga_ds831.txt")

f("thm-045", "compact placement penalty", "Closely packing chiplets to minimise wirelength leads to thermally inefficient 2.5D designs (TAP-2.5D premise)", "", "",
  "closely packs the chiplets to minimize wirelength, but this leads to a thermallyinefficient design", "thermal/tap25d_date2021.raw.txt",
  notes="Hyphenation lost in extraction ('thermally-inefficient').")
f("thm-046", "TIM II BLT", "TIM II can dominate when its bondline thickness is large", "", "",
  "The TIM II interface can become a dominant factor if the bond line thickness (BLT) is large", "thermal/ecool_lidded_vs_bare_die_2012.txt", conf="medium")
f("thm-047", "warpage vs die size", "Larger dies show greater package warpage from Si/laminate CTE mismatch, varying TIM bondline", "", "",
  "Larger die sizes exhibit greater package warpage due to the difference in thermal expansion coefficients between silicon and laminate materials.", "thermal/ecool_lidded_vs_bare_die_2012.txt", conf="medium")

f("thm-048", "interposer coupling", "Logic-HBM coupling is more pronounced through a silicon interposer than a glass one", "", "",
  "particularly more pronounced in the silicon interposer substrate than glass", "thermal/itherm2024_dual_sided_bspdn.raw.txt")


def load_fetchlog():
    out = {}
    path = os.path.join(ROOT, "FETCHLOG.tsv")
    with open(path, encoding="utf-8") as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if len(row) < 7:
                continue
            ts, rel, code, size, lines, sha, url = row[:7]
            stem = os.path.splitext(os.path.basename(rel))[0]
            out[stem] = dict(retrieved_utc=ts, url=url, raw_file=rel, http=code, sha256=sha)
    return out


def main():
    log = load_fetchlog()
    lanes = {}
    for fact in F:
        stem = os.path.basename(fact["file"]).split(".")[0]
        meta = SRC.get(stem)
        if meta is None:
            raise SystemExit(f"no source metadata for {stem} ({fact['fact_id']})")
        fl = log.get(stem, {})
        rec = dict(fact)
        rec.update(title=meta[0], publisher=meta[1], date=meta[2], source_type=meta[3],
                   url=fl.get("url", ""), raw_file=fl.get("raw_file", ""), retrieved_utc=fl.get("retrieved_utc", ""))
        if rec["render"] is None:
            del rec["render"]
        if meta[3] == "secondary" and rec["confidence"] == "high":
            rec["confidence"] = "medium"
        lane = fact["file"].split("/")[0]
        lanes.setdefault(lane, []).append(rec)
    for lane, recs in lanes.items():
        with open(os.path.join(ROOT, lane, "FACTS.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
            for rec in recs:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(lane, len(recs))
    used = sorted({os.path.basename(x["file"]).split(".")[0] for x in F})
    with open("C:/tmp/lane1-scripts/used_sources.json", "w", encoding="utf-8") as fh:
        json.dump({s: SRC[s] for s in used}, fh, indent=1)
    print("sources used:", len(used))


if __name__ == "__main__":
    main()
