# Sources for lane 1 (anatomy)

Everything the lane relied on is saved under `evidence/`, and nothing there has been deleted. Each source is kept in three forms:

- **raw download:** `.html` or `.pdf`, byte-for-byte as fetched;
- **text extraction:** `.txt`. PDFs also have `.raw.txt` in reading order;
- **page renders:** for slides whose tables or units survive only as graphics (`evidence/*/renders/*.png`).

**How the facts were checked**

- `evidence/<lane>/FACTS.jsonl` holds one record per fact. Each record has a verbatim quote, the evidence file, URL, title, publisher, date, source type, capture method, confidence and notes.
- `tools/verify_facts.py` was run over all 176 facts: **0 failures**.
  - A plain fact passes when its quote is found in the cited text file, after whitespace, case and dash normalisation.
  - A `render` fact passes when its rendered page exists and its anchor quote (if any) is found. Its value is read from the image, so it is marked VISUAL.
- Numbers in `parts.json`, `thermal_path.md` and `our_model_mapping.md` cite these fact ids. The readable report could not be written here (see the agent's note); its content went to the parent agent.

**Safety and exclusions**

- **Downloaded pages are untrusted data.** They were only parsed: HTML went through a stdlib HTML parser, PDFs through `pdftotext` and PyMuPDF rendering, always via `python -I` with scripts kept outside `evidence/`. Nothing from them was executed.
- **No MicroDuck or Pollen material is used.**
- **Read-only on repos.** `H:/sentilab` was read at `origin/main` 46791be through `git show` and `git grep`; numbered excerpts are in `evidence/repo/`.
- **Primary vs secondary.** Primary means standards bodies, vendor pages, data sheets, white papers and press releases, conference papers and slides, and patents. Secondary means news, blogs, analyst and distributor pages; facts from those are capped at medium confidence.

## Sources used (cited by at least one fact)

| # | Source slug (evidence file stem) | Title | Publisher / author | Date | Type | Facts | URL | Retrieved (UTC) | SHA-256 of raw file |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `hbm/broadcom_stratadnx_hbm_appnote` | StrataDNX HBM Configuration and Debugging Guide (DNX-HBM-AN101-PUB) | Broadcom | 2021-12-10 | primary | hbm-045 | https://docs.broadcom.com/doc/StrataDNX-HBM-Configuration-and-Debugging-Guide-AN | 2026-10-31T19:16:27Z | `0fcc232a67452b2b5b5137d176648e3d5226770fd1db69bda9250b2052f42060` |
| 2 | `hbm/cadence_hbm3_phy_page` | HBM3 PHY (product page) | Cadence | accessed 2026-10-31 | primary | hbm-040 | https://www.cadence.com/en_US/home/tools/silicon-solutions/design-ip/memory-interface-and-storage-ip/hbm-phy/hbm3.html | 2026-10-31T19:24:07Z | `e9982fef51733ababf7572fa2b62321a75121a9f9000fe1db7e9692b3fa82245` |
| 3 | `hbm/formfactor_swtw2016_hbm_probing` | Verification of HBM through Direct Probing on MicroBumps (M. Loranger, SWTW 2016) | FormFactor / SW Test Workshop | 2016-06 | primary | hbm-032 | https://www.swtest.org/swtw_library/2016proc/PDF/S01_02_Loranger_SWTW2016.pdf | 2026-10-31T19:16:26Z | `de575d10c69ec7a70369829b4e5c81df5a6110e5c4929f73dcbea1fe10bcf7ab` |
| 4 | `hbm/imaps_hbm_underfill_tsv_study` | A Study on the Effectiveness of Underfill in the High Bandwidth Memory with TSV (W.-S. Lee et al., IMAPS 2013) | IMAPS (authors from SK hynix) | 2013-10 | primary | hbm-033, hbm-046 | https://imapsource.org/api/v1/articles/57356-a-study-on-the-effectiveness-of-underfill-in-the-high-bandwidth-memory-with-tsv.pdf | 2026-10-31T19:25:17Z | `300d4374a1b1033a106e65e8e65875a9a111e135c0ceaf0bfd49fa10cd402d62` |
| 5 | `hbm/jedec_hbm3_pr_2022` | JEDEC Publishes HBM3 Update to High Bandwidth Memory (HBM) Standard (JESD238) | JEDEC | 2022-01-27 | primary | hbm-001, hbm-002, hbm-003, hbm-004 | https://www.jedec.org/news/pressreleases/jedec-publishes-hbm3-update-high-bandwidth-memory-hbm-standard | 2026-10-31T19:09:42Z | `97af2be84234d9c569a1af53af94abbb19f37e56980ed42903eb7e63e9e5be78` |
| 6 | `hbm/jedec_hbm4_pr_2025` | JEDEC and Industry Leaders Collaborate to Release JESD270-4 HBM4 Standard | JEDEC | 2025-04-16 | primary | hbm-005, hbm-006, hbm-007, hbm-008 | https://www.jedec.org/news/pressreleases/jedec%C2%AE-and-industry-leaders-collaborate-release-jesd270-4-hbm4-standard-advancing | 2026-10-31T19:09:42Z | `ecd0157a7eca89c9b6565e7a6e2483dbe5282b9501d8978ec46de2399ffe8b6a` |
| 7 | `hbm/micron_hbm3e_product_brief` | Product Brief - Micron HBM3E (Rev C 10/2023) | Micron Technology | 2023-10 | primary | hbm-018, hbm-019, hbm-020, hbm-021 | https://assets.micron.com/adobe/assets/urn:aaid:aem:b710d8f2-7f66-44c1-a234-456e2b986347/renditions/original/as/hbm3e-product-brief.pdf | 2026-10-31T19:22:14Z | `c9c99fbc7f3ca759b22add23c7a5151340d559954919c30092a966ac6e51da48` |
| 8 | `hbm/rambus_hbm3e_controller_page` | HBM3E Controller (product page) | Rambus | accessed 2026-10-31 | primary | hbm-039 | https://www.rambus.com/interface-ip/hbm/hbm3-controller/ | 2026-10-31T19:24:07Z | `9b72644355120940620040db25407d16a918c6cc1ccbdb755c3ffb1b044e8b4c` |
| 9 | `hbm/samsung_12layer_3dtsv_2019` | Samsung Electronics Develops Industry's First 12-Layer 3D-TSV Chip Packaging Technology | Samsung Global Newsroom | 2019-10-07 | primary | hbm-034, hbm-035 | https://news.samsung.com/global/samsung-electronics-develops-industrys-first-12-layer-3d-tsv-chip-packaging-technology | 2026-10-31T19:28:18Z | `9467e2ccdf70dc1d745bc0309afc707def98cccfeef4d0a40f7190c3a6ea7a0e` |
| 10 | `hbm/samsung_hbm3e_12h_2024` | Samsung Develops Industry-First 36GB HBM3E 12H DRAM | Samsung Global Newsroom | 2024-02-27 | primary | hbm-014, hbm-015, hbm-016, hbm-017 | https://news.samsung.com/global/samsung-develops-industry-first-36gb-hbm3e-12h-dram | 2026-10-31T19:12:24Z | `d98fbc86cd579388d4f905b0165210724c280c78f466dfdbd327453247b75601` |
| 11 | `hbm/skhynix_hbm3e_12h_2024` | SK hynix Begins Volume Production of the World's First 12-Layer HBM3E | SK hynix Newsroom | 2024-09-26 | primary | hbm-010, hbm-011, hbm-012, hbm-013 | https://news.skhynix.com/en/sk-hynix-begins-volume-production-of-the-world-first-12-layer-hbm3e/ | 2026-10-31T19:12:24Z | `95786f28de43387cba14c1ea0cb71d273d136bcb32aaaf0bd857cd39c78c6b57` |
| 12 | `hbm/skhynix_hc28_hbm_tutorial` | The Era of High Bandwidth Memory (K. Tran, Hot Chips 28 tutorial) | SK hynix / Hot Chips | 2016-08 | primary | hbm-022, hbm-023, hbm-024, hbm-025, hbm-047, hbm-048 | https://old.hotchips.org/wp-content/uploads/hc_archives/hc28/HC28.21-Tutorial-Epub/HC28.21.1-Next-Gen-Memory-Epub/HC28.21.130-High-Bandwidth-KEVIN_TRAN-SKHYNIX-VERSION_FINAL-dcrp-t1-4_.pdf | 2026-10-31T19:16:27Z | `a5cfc1793a3ae128144ff62786cca9195c659581d1a33ddb6131b23eb2c0563b` |
| 13 | `hbm/skhynix_iedm23_hbm_packaging` | Advanced Packaging Technologies in Memory Applications for Future Generative AI Era (K.-I. Moon, H.-Y. Son, K. Lee; IEDM 2023 paper 15-6 handout) | SK hynix / IEEE IEDM | 2023-12 | primary | hbm-026, hbm-027, hbm-028, hbm-029, hbm-030, hbm-031 | https://iedm23.mapyourshow.com/mys_shared/iedm23/handouts/15-6_Tue_14482.pdf | 2026-10-31T19:16:25Z | `e48f80e713309d19bdc847c32c65edd0dca87e727db50e2b54d2c8de41eaf403` |
| 14 | `hbm/skhynix_tsmc_hbm4_mou_2024` | SK hynix Partners with TSMC to Strengthen HBM Technological Leadership | SK hynix Newsroom | 2024-04-19 | primary | hbm-036 | https://news.skhynix.com/en/sk-hynix-partners-with-tsmc-to-strengthen-hbm-technological-leadership/ | 2026-10-31T19:24:07Z | `cf603aefb8216c20c0673e113fdc1752e94e2a55fb946ad51474ff72d94ece31` |
| 15 | `hbm/synopsys_hbm3_phy_page` | HBM3 PHY IP (product page) | Synopsys | accessed 2026-10-31 | primary | hbm-038 | https://www.synopsys.com/designware-ip/interface-ip/hbm/hbm3-phy.html | 2026-10-31T19:24:07Z | `0a3055efa7f89839aae57696018b0c985c61ce4fa3cbf426ad6e43bb370efe48` |
| 16 | `hbm/tomshw_skhynix_hbm4_16hi` | SK hynix shows 16-Hi HBM4 memory for AI accelerators | Tom's Hardware | 2026-01 | secondary | hbm-037 | https://www.tomshardware.com/tech-industry/sk-hynix-shows-16-hi-hbm4-memory-for-ai-accelerators-48-gb-at-10-gt-s-over-a-2-048-interface | 2026-10-31T19:22:13Z | `fb225a97d01ac177556567a66639ce4e4fa4d756f657bcc7268313674c7a4e67` |
| 17 | `hbm/trendforce_hbm4_775um_2025` | JEDEC Finalizes HBM4 Standard, Potentially Easing Pressure on Hybrid Bonding Adoption (citing ZDNet) | TrendForce | 2025-04-21 | secondary | hbm-009 | https://www.trendforce.com/news/2025/04/21/news-jedec-finalizes-hbm4-standard-potentially-easing-pressure-on-hybrid-bonding-adoption/ | 2026-10-31T19:09:43Z | `d82c2be876e677e85add0ae1fe6ec4c3a20412cb415821713da597573dd35e45` |
| 18 | `hbm/ucie_buss25_dassharma` | UCIe (D. Das Sharma), IEEE Build-Up Substrate Symposium BUSS'25 | Intel / UCIe Consortium / IEEE | 2025-05-08 | primary | hbm-043, hbm-044 | https://attend.ieee.org/buss/wp-content/uploads/sites/693/F08-DasSharma.pdf | 2026-10-31T19:14:04Z | `5353272432ce8bdebf85664477b36f5cfd0068e5a83ab54fcbb43f5d1628f2cb` |
| 19 | `hbm/ucie_hc2023_electrical` | UCIe Electrical, Form Factor and Compliance (Hot Chips 2023 tutorial) | UCIe Consortium / Hot Chips | 2023-08 | primary | hbm-041, hbm-042 | https://www.hc2023.hotchips.org/assets/program/tutorials/ucie/Electrical%20Form%20Factor%20and%20Compliance.pdf | 2026-10-31T19:14:05Z | `64acd314723af2ecf0e7e9a0c616de47d114d5da94272fd24e304b953e8e17ce` |
| 20 | `packaging/amkor_fcbga_ds831` | Flip Chip BGA (FCBGA) data sheet DS831 | Amkor Technology | accessed 2026-10-31 | primary | pkg-022, pkg-023, pkg-024, pkg-025, pkg-026, pkg-027, pkg-055 | https://amkor.com/wp-content/uploads/2018/02/FCBGA_DS831.pdf | 2026-10-31T19:14:04Z | `e38280726a8b1749e9dc07fd1f7edea06489f62545e5605948716211dc3d92ad` |
| 21 | `packaging/amkor_flipchip_ts102` | Flip Chip Packaging technology sheet TS102 | Amkor Technology | accessed 2026-10-31 | primary | pkg-028, pkg-029, pkg-030, pkg-053, pkg-054 | https://amkormarcomexternal.blob.core.windows.net/amkordotcom/wp-content/uploads/2018/02/Flip_Chip_TS102.pdf | 2026-10-31T19:14:05Z | `27cc1df55d58ecf9316fccffe7db97325d75e0587f0019411d92e731a47a99f3` |
| 22 | `packaging/google_patent_us10083920_stiffener` | US10083920B1 Package stiffener for protecting semiconductor die (Google Patents) | Google LLC (assignee) | 2018 | primary | pkg-039, pkg-040 | https://patents.google.com/patent/US10083920B1/en | 2026-10-31T19:20:39Z | `7efce1a6268d27bb27f736c6ea60116279d1d055672e0ccfebc8007169a63003` |
| 23 | `packaging/intel_qr_vol6_adv_packaging` | Quality & Reliability Vol. 6: Intel Advanced Packaging Technology | Intel | accessed 2026-10-31 | primary | pkg-035, pkg-036, pkg-037 | https://cdrdv2-public.intel.com/826148/Volume%206%20Intel%20Advanced%20Packaging%20Technology.pdf | 2026-10-31T19:28:18Z | `420599cdface05250f356c1fa7c37c3f6c2b85864427751734e10f2e58fd71ba` |
| 24 | `packaging/kyocera_fcbga_organic_substrates` | Package Substrate Solutions - FCBGA Technology (roadmap) | Kyocera Europe | 2024 | primary | pkg-031, pkg-032, pkg-033, pkg-034 | https://sweden.kyocera.com/uploads/eu/DB_SC_FCBGA_organic_substrates_A4_2024_web.pdf | 2026-10-31T19:25:19Z | `21c29e2e204946a30c6409c8967802bd134841f8a1cdb80cb72acadf3a03b53d` |
| 25 | `packaging/mediaupdate_iedm2019_part2` | IEDM 2019 (Part 2): 3D Packaging Innovation and Memory Technology (blog report of TSMC iCap paper) | mediaupdate2019 (blog) | 2019-12-31 | secondary | pkg-046 | https://mediaupdate2019.wordpress.com/2019/12/31/iedm2019-part2-3d-packaging-innovation-and-memory-technology-ferroelectrics/ | 2026-10-31T19:33:05Z | `19a169c271b5f4083837202aea3ebb731b5a041673381f11b4d8caff3e1f99cc` |
| 26 | `packaging/microchip_fcbga196_c04_25015` | 196-Ball FCBGA 15x15x1.4 mm package drawing C04-25015 Rev A | Microchip Technology | 2021 | primary | pkg-049 | https://ww1.microchip.com/downloads/aemDocuments/documents/package-outline-drawings/c04-25015a.pdf | 2026-10-31T19:35:51Z | `79eaace1d089fe00db80c9326614a3a60e0e2026d4397f790369fc6c2aca3888` |
| 27 | `packaging/renesas_alg784_fcbga_29mm` | ALG 784 package outline, FCBGA 29.0 x 29.0 mm body, 1.00 mm ball pitch (flat lid), PSC-4627 | IDT / Renesas | 2015-11-18 | primary | pkg-050 | https://www.renesas.com/en/document/psc/alg-784-package-outline-fcbga-290-x-290mm-body-100-mm-ballpitch-fcbga | 2026-10-31T19:35:52Z | `93ecbbc52a3818ceb3d19bf7d80d38fadfed63dd730c8510fbe46bbc87456cf1` |
| 28 | `packaging/tomshw_abf_substrates_2026` | The state of ABF substrates in data center silicon in 2026 | Tom's Hardware | 2026 | secondary | pkg-047, pkg-048, prd-018 | https://www.tomshardware.com/tech-industry/semiconductors/the-state-of-abf-substrates-in-data-center-silicon-in-2026-solving-the-supply-crunch-and-material-wall-beneath-every-ai-accelerator | 2026-10-31T19:20:39Z | `8d8612f6c2b04db79abce0b8fb110f89f690b4f9ee59d1e671f94de4034836f9` |
| 29 | `packaging/tsmc_cowos_page` | CoWoS (3DFabric technology page) | TSMC | accessed 2026-10-31 | primary | pkg-001, pkg-002, pkg-003, pkg-004, pkg-005, pkg-006, pkg-007, pkg-008, pkg-009 | https://3dfabric.tsmc.com/english/dedicatedFoundry/technology/cowos.htm | 2026-10-31T19:09:42Z | `2347cc2285c093d48ee50f5ed0753958302a925866406575d97d5a41e7a2768d` |
| 30 | `packaging/tsmc_hotchips33_packaging_tutorial` | TSMC Packaging Technologies for Chiplets and 3D (Hot Chips 33 tutorial) | TSMC / Hot Chips | 2021-08-19 | primary | pkg-011, pkg-012, pkg-013, pkg-014, pkg-015, pkg-016, pkg-017, pkg-051, pkg-052 | https://hc33.hotchips.org/assets/program/tutorials/2021%20HotChips%20TSMC%20Packaging%20Technologies%20for%20Chiplets%20and%203D_0819%20publish_public.pdf | 2026-10-31T19:09:43Z | `b9c11d1a52ed15ee888486202dee286456fc6299a54cd1504885bee32c28d113` |
| 31 | `packaging/tsmc_patent_us20200381391_cowos` | US20200381391A1 CoWoS Structures and Methods Forming Same (Google Patents) | TSMC (assignee) | 2020 | primary | pkg-038 | https://patents.google.com/patent/US20200381391A1/en | 2026-10-31T19:24:07Z | `85fd16686742533571d742d1a364d11dd0e05a7768c52aa11288a4bb9007d47f` |
| 32 | `packaging/tsmc_soic_page` | TSMC-SoIC (3DFabric technology page) | TSMC | accessed 2026-10-31 | primary | pkg-010 | https://3dfabric.tsmc.com/english/dedicatedFoundry/technology/SoIC.htm | 2026-10-31T19:09:43Z | `a2e706a4e161e2e6ec8be9a500ac5bf22f260d17bf105f3fb13481f34ad1d337` |
| 33 | `packaging/vicor_vpd_genai_article` | High-Current-Density Power Modules Mitigate the Environmental Impact of Power-Intensive GenAI | Vicor | accessed 2026-10-31 | primary | pkg-041, pkg-042, pkg-043, pkg-044, pkg-045 | https://www.vicorpower.com/resource-library/articles/high-performance-computing/modules-mitigate-the-environmental-impact-of-genai | 2026-10-31T19:20:39Z | `e5e860e6724b5b37f9abc86f21fd908c1e72c6bbd21ebdce16173f8605f0911b` |
| 34 | `packaging/xilinx_cpmt1104b` | Stacked Silicon Interconnect Technology (Xilinx; IEEE CPMT chapter presentation) | Xilinx / IEEE CPMT | 2011-04-28 | primary | pkg-018 | https://ewh.ieee.org/soc/cpmt/presentations/cpmt1104b.pdf | 2026-10-31T19:14:06Z | `255b5bcf0c8676cfd011981934d6c4105b69bb31a18f7a528696da414f0e84e9` |
| 35 | `packaging/xilinx_wp380` | Xilinx Stacked Silicon Interconnect Technology Delivers Breakthrough FPGA Capacity, Bandwidth, and Power Efficiency (WP380) | Xilinx / AMD | 2012 | primary | pkg-019, pkg-020 | https://docs.amd.com/api/khub/documents/jcXzYXzAZP1LXWncl0_Oig/content | 2026-10-31T19:14:05Z | `876f5a40ca727a93d985b726eea482dc592b3b5a96a2d88cc5df59bb03bde867` |
| 36 | `products/amd_cdna3_whitepaper` | AMD CDNA 3 Architecture white paper | AMD | 2024-2025 | primary | prd-019, prd-020, prd-021, prd-022, prd-023 | https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/white-papers/amd-cdna-3-white-paper.pdf | 2026-10-31T19:12:24Z | `a0811d04f101f9127bd183d6e228f462b6fd988b0e0e6d263a25e4bed712f593` |
| 37 | `products/amd_hc2024_mi300x` | AMD Instinct MI300X Generative AI Accelerator and Platform Architecture (A. Smith, Hot Chips 2024) | AMD / Hot Chips | 2024-08 | primary | prd-024, prd-025 | https://hc2024.hotchips.org/assets/program/conference/day1/23_HC2024.AMD.MI300X.ASmith(MI300X).v1.Final.20240817.pdf | 2026-10-31T19:12:25Z | `795e9f2b7fd0d541967c3dbe4293123f05a89c3e4f2e101608b1f97d13180d61` |
| 38 | `products/huawei_hc31_davinci_slides` | DaVinci: A Scalable Architecture for Neural Network Computing (Heng Liao, Hot Chips 31) | Huawei / Hot Chips | 2019-08 | primary | prd-001, prd-002, prd-003, prd-004, prd-005, prd-006, prd-007 | https://www.old.hotchips.org/hc31/HC31_1.11_Huawei.Davinci.HengLiao_v4.0.pdf | 2026-10-31T19:09:43Z | `c9fc6953008d96deface0b66a416cb574672131066a097d625b9f1794aa918b6` |
| 39 | `products/nvidia_blackwell_arch_page` | NVIDIA Blackwell Architecture (technology page) | NVIDIA | accessed 2026-10-31 | primary | prd-014, prd-017 | https://www.nvidia.com/en-us/data-center/technologies/blackwell-architecture/ | 2026-10-31T19:14:04Z | `9e555b398cd24da846db97a4f74344f6f3da4f9ccae6a89fcbec4c7c392cd529` |
| 40 | `products/nvidia_blackwell_ultra_blog` | Inside NVIDIA Blackwell Ultra: The Chip Powering the AI Factory Era | NVIDIA Technical Blog | 2025 | primary | prd-015, prd-016 | https://developer.nvidia.com/blog/inside-nvidia-blackwell-ultra-the-chip-powering-the-ai-factory-era/ | 2026-10-31T19:14:05Z | `b77b0fe6ed2c37b267b50fb11682c78979747a21e354ff7d003987399ab01b5e` |
| 41 | `products/nvidia_h100_datasheet` | NVIDIA H100 Tensor Core GPU datasheet (NVIDIA document; third-party mirror) | NVIDIA | 2023 | primary | prd-013 | https://www.megware.com/fileadmin/user_upload/LandingPage%20NVIDIA/nvidia-h100-datasheet.pdf | 2026-10-31T19:12:25Z | `e636e226f957b4540715f4def7fb3ca933098569c037fd8b348756997b1f444b` |
| 42 | `products/nvidia_h100_whitepaper_v102` | NVIDIA H100 Tensor Core GPU Architecture whitepaper v1.02 (NVIDIA document; third-party mirror) | NVIDIA | 2022 | primary | prd-009, prd-010, prd-011, prd-012 | https://www.hpctech.co.jp/assets/images/info/catalog/pdf/gtc22-whitepaper-hopper_v1.02.pdf | 2026-10-31T19:12:27Z | `2023ed533a66ea61ce9c8e84ff621c7ac595fd8d87c1a7aedf9bccd872fe6458` |
| 43 | `products/sth_ascend910_hc31` | Huawei Ascend 910 Provides a NVIDIA AI Training Alternative | ServeTheHome | 2019-08 | secondary | prd-008 | https://www.servethehome.com/huawei-ascend-910-provides-a-nvidia-ai-training-alternative/ | 2026-10-31T19:09:43Z | `3ef5c9e7b2f1a5a58b04c84aac26ade2100b1fcb0550adb762178c5eb9ff4a83` |
| 44 | `thermal/ecool_lidded_vs_bare_die_2012` | Lidded Versus Bare Die Flip Chip Package: Impact on Thermal Performance | Electronics Cooling magazine | 2012-06 | secondary | thm-041, thm-046, thm-047 | https://www.electronics-cooling.com/2012/06/lidded-versus-bare-die-flip-chip-package-impact-on-thermal-performance/ | 2026-10-31T19:20:40Z | `b84a1e6883e4660abb0b9150367eeb15504a4a7b9e2b4f6654d1f9aefb900ac4` |
| 45 | `thermal/ecool_si_thermal_conductivity_1998` | The thermal conductivity of silicon | Electronics Cooling magazine | 1998-05 | secondary | thm-017, thm-018 | https://www.electronics-cooling.com/1998/05/the-thermal-conductivity-of-silicon/ | 2026-10-31T19:20:40Z | `e907bcdc7f58c275c71cc6832af238581c40bf9f4446cf81ad8304cd47e420eb` |
| 46 | `thermal/hotspot60_tr_https` | HotSpot 6.0: Validation, Acceleration and Extension (R. Zhang, M. Stan, K. Skadron; UVA TR CS-2015-04) | University of Virginia | 2015 | primary | thm-009, thm-010, thm-011, thm-012 | https://www.cs.virginia.edu/~skadron/Papers/HotSpot60_TR.pdf | 2026-10-31T19:10:10Z | `e3ca1b312f8e57a186e2dd6946f9f836af9d19a5facc27d5e42a7026475403c4` |
| 47 | `thermal/iceotope_1000w_whitepaper` | Chip cooling at 1000W and beyond (whitepaper page) | Iceotope | accessed 2026-10-31 | primary | thm-039 | https://www.iceotope.com/company/resources/chip-cooling-1000w-beyond | 2026-10-31T19:24:07Z | `1c731361008f77729a6b0d1971df3b9700208ec20ec65a15952f63768ac491d1` |
| 48 | `thermal/ieee_spectrum_hbm_on_gpu_imec` | HBM on GPU: Thermal Challenges and Solutions (reporting imec, IEDM 2025) | IEEE Spectrum | 2026 | secondary | thm-036, thm-037 | https://spectrum.ieee.org/hbm-on-gpu-imec-iedm | 2026-10-31T19:16:26Z | `61bd7904936ef1b38ef16215028df2ff5777d44d7337d4171664edbc70fd8f8a` |
| 49 | `thermal/imaps_xilinx_thermal_tsv_interposer` | Advanced Thermal Study of Very High Power TSV Interposer and Interconnects for 28nm Technology FPGA (B. Banijamali, S. Ramalingam, R. Chaware; IMAPS 2011) | Xilinx / IMAPS | 2011-10 | primary | pkg-021, thm-013, thm-014, thm-015, thm-016 | https://imapsource.org/api/v1/articles/56953-advanced-thermal-study-of-very-high-power-tsv-interposer-and-interconnects-for-28nm-technology-fpga.pdf | 2026-10-31T19:14:04Z | `2048f6a2a9d1eaf9980d1f9d802e863de08d9574d881f280899086e8924dcd78` |
| 50 | `thermal/indium_tim_products_page` | Thermal Interface Materials (product page) | Indium Corporation | accessed 2026-10-31 | primary | thm-020 | https://www.indium.com/products/thermal-interface-materials/ | 2026-10-31T19:19:08Z | `e66cdae9098524ba2f80c38f758e9a890e87a513fe0c3dd14292c511dea8a470` |
| 51 | `thermal/ioffe_si_thermal_http` | Thermal properties of Silicon (Si), NSM Archive | Ioffe Institute | accessed 2026-10-31 | primary | thm-019 | http://www.ioffe.ru/SVA/NSM/Semicond/Si/thermal.html | 2026-10-31T19:19:19Z | `e87101fb40e1036ff5d91eb8d41696a7529902b2e7eb50cfc5666e52e01a27bd` |
| 52 | `thermal/itherm2024_dual_sided_bspdn` | Thermal Analysis of Dual-sided Cooling for Backside Power Delivery Networks on 2.5D Glass/Silicon Interposer Package (F. Xie, S. Lyu, T. Wei; ITherm 2024, author-hosted revised version) | Purdue University / IEEE ITherm | 2024 | primary | thm-029, thm-030, thm-031, thm-032, thm-033, thm-034, thm-035, thm-043, thm-048 | https://s-pack.org/wp-content/uploads/2024/07/ITherm-2024-Feifan_Xie-revised_version.pdf | 2026-10-31T19:16:29Z | `90a215de76f95ac167542623804dbdf1a1ea73b2a375f21aee7c3461cfa85f26` |
| 53 | `thermal/krayden_uf8807` | LOCTITE ECCOBOND UF 8807 (distributor product page) | Krayden / CAPLINQ (Henkel product) | accessed 2026-10-31 | secondary | thm-023 | https://www.krayden.com/products/eccobond-uf8807 | 2026-10-31T19:19:09Z | `a879f8cd009cf1c27b233ff4550dcb209b1dce985e080824ede3210dcf470920` |
| 54 | `thermal/ocp_oai_liquid_cooling_guidelines` | OAI System Liquid Cooling Guidelines (Mar 2023 update) | Open Compute Project | 2023-03-03 | primary | thm-040, thm-042, thm-044 | https://www.opencompute.org/documents/oai-system-liquid-cooling-guidelines-in-ocp-template-mar-3-2023-update-pdf/ | 2026-10-31T19:24:07Z | `531d457d34a0a1aad82468cbbcb7ba0a1e21f74c5a0b101da42a3dc8ee748f52` |
| 55 | `thermal/solderconnection_sac305` | PURALLOY SAC305 lead-free solid feed wire (product page) | Solder Connection | accessed 2026-10-31 | primary | thm-025 | https://www.solderconnection.com/product/puralloy-sac305-lead-free-solid-feed-wire/ | 2026-10-31T19:22:14Z | `33a05b4f51076c511dd3b0b6dce6695a6f5ec5cfd74e1a298feb9c1cefde71d1` |
| 56 | `thermal/solstice_ptm7950_tds` | PTM7950 Phase Change Material technical data sheet | Solstice Advanced Materials (formerly Honeywell) | accessed 2026-10-31 | primary | thm-021, thm-022 | https://prod-edam.solstice.com/content/dam/honeywell-edam/pmt/oneam/en-us/electronic-materials/thermal-interface-materials/documents/100600-esm-tds-ptm7950-pcm-ltr-en.pdf | 2026-10-31T19:22:13Z | `15687e0574dc427a6b8fef49a6d9477f73356fae744fcdef17f12267d2d023ed` |
| 57 | `thermal/sumikon_g700l` | SUMIKON EME-G700LA Type L typical properties | Sumitomo Bakelite (mirrored by mirrorsemi.com) | accessed 2026-10-31 | primary | thm-024 | https://www.mirrorsemi.com/pdf/G700L.pdf | 2026-10-31T19:19:08Z | `5b6f785b7824958b34c546b6da04e5eb65df9da965cc627c4831d175f0dbe446` |
| 58 | `thermal/tap25d_date2021` | TAP-2.5D: A Thermally-Aware Chiplet Placement Methodology for 2.5D Systems (Y. Ma et al., DATE 2021) | Boston University / DATE | 2021 | primary | thm-001, thm-002, thm-003, thm-004, thm-005, thm-006, thm-007, thm-008, thm-045 |  |  | `` |
| 59 | `thermal/ucla_embedded_isolators_2p5d` | Optimizing Thermal Performance in 2.5D Systems Using Embedded Isolators (G. Karfakis et al., UCLA / Georgia Tech; author-hosted) | UCLA NanoCAD | 2025 | primary | thm-026, thm-027, thm-028 | https://nanocad.ee.ucla.edu/wp-content/papercite-data/pdf/j84.pdf | 2026-10-31T19:16:27Z | `dd54c0e1a499e455ddd0a2f336d7c6c4581ce0a6ed39b65c8e2f42c519bfe514` |
| 60 | `thermal/vertiv_coolant_temp_roadmap` | Keep it at 30C: A roadmap for the future chip coolant temperature (blog) | Vertiv | 2026 | secondary | thm-038 | https://www.vertiv.com/en-us/insights/articles/blog-posts/a-roadmap-for-the-future-chip-coolant-temperature/ | 2026-10-31T19:16:27Z | `e8fdaefbbf81f524c174ba847805bc4bc9f3bca48ffa7a793ac4745848034a31` |

## Downloaded but not cited (kept as evidence; includes failed fetches)

| File | HTTP | Bytes | URL | Note |
|---|---|---|---|---|
| `thermal/hotspot60_tr.pdf` | 000 | 0 | http://www.cs.virginia.edu/~skadron/Papers/HotSpot60_TR.pdf | fetch failed or blocked |
| `products/amd_mi300x_datasheet.pdf` | 200 | 1855742 | https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/data-sheets/amd-instinct-mi300x-data-sheet.pdf | not needed for a cited fact |
| `products/nvidia_hopper_indepth_blog.html` | 200 | 451985 | https://developer.nvidia.com/blog/nvidia-hopper-architecture-in-depth/ | not needed for a cited fact |
| `products/nvidia_blackwell_pr_2024.html` | 200 | 95863 | https://nvidianews.nvidia.com/news/nvidia-blackwell-platform-arrives-to-power-a-new-era-of-computing | not needed for a cited fact |
| `packaging/imaps_xilinx_quality_tsv.pdf` | 200 | 957311 | https://imapsource.org/article/56305-quality-and-reliability-of-3d-tsv-interposer-and-fine-pitch-solder-micro-bumps-for-28nm-technology.pdf | not needed for a cited fact |
| `packaging/ieee_xplore_tsmc_icap_iedm2019.html` | 202 | 0 | https://ieeexplore.ieee.org/document/8993498/ | fetch failed or blocked |
| `packaging/wikichip_tsmc_icap.html` | 000 | 0 | https://fuse.wikichip.org/news/3144/tsmc-digs-trenches-in-search-of-higher-performance/ | fetch failed or blocked |
| `thermal/indium_tim_bga_pds100082.pdf` | 200 | 201067 | https://www.indium.com/wp-content/uploads/2025/01/Solder-Thermal-Interface-Materials-for-BGA-Packages-PDS-100082-R1.pdf | not needed for a cited fact |
| `thermal/indium_hp_tims_handout.pdf` | 200 | 1137952 | https://www.indium.com/wp-content/uploads/2025/09/High-Performance-TIMs-Handout-99541-R1.pdf | not needed for a cited fact |
| `thermal/ioffe_si_thermal.html` | 000 | 0 | https://www.ioffe.ru/SVA/NSM/Semicond/Si/thermal.html | fetch failed or blocked |
| `thermal/henkel_uf4550htc_tds.pdf` | 200 | 13897 | https://www.mouser.lt/datasheet/2/773/LOCTITE_ECCOBOND_UF_4550HTC_en_GL-3433461.pdf | not needed for a cited fact |
| `thermal/indium_metal_tims_brochure.pdf` | 200 | 1855907 | https://scp.indium.com/download-files/metal_thermal_interface_materials_4pg_98678_a4_r2 | not needed for a cited fact |
| `packaging/eenews_ai_cards_1000a.html` | 200 | 283279 | https://www.eenewseurope.com/en/designing-ai-accelerator-cards-with-currents-over-1000a/ | not needed for a cited fact |
| `packaging/vicor_vpd_enables_article.html` | 200 | 89715 | https://www.vicorpower.com/resource-library/articles/high-performance-computing/vertical-power-delivery-enables-cutting-edge-processing | not needed for a cited fact |
| `hbm/micron_hbm3e_page.html` | 200 | 353611 | https://www.micron.com/products/memory/hbm/hbm3e | not needed for a cited fact |
| `thermal/solstice_ptm7950_page.html` | 200 | 214499 | https://www.solstice.com/us/en/products/advanced-semiconductor-materials/thermal-management/phase-change-materials/ptm7950 | not needed for a cited fact |
| `thermal/indium_liquid_metal_page.html` | 200 | 267421 | https://www.indium.com/products/thermal-interface-materials/liquid-metal/ | not needed for a cited fact |
| `thermal/accelsius_warm_water_whitepaper.pdf` | 200 | 573071 | https://accelsius.com/wp-content/uploads/Warm-Water-Ready-Accelsius-Whitepaper.pdf | not needed for a cited fact |
| `thermal/mdpi_review_2p5d_3d_thermal_2025.html` | 403 | 400 | https://www.mdpi.com/2673-4117/6/12/373 | fetch failed or blocked |
| `hbm/mdpi_review_hbm_hybrid_bonding_thermal_2025.html` | 403 | 402 | https://www.mdpi.com/2079-9292/14/13/2682 | fetch failed or blocked |
| `packaging/nxp_an13656_fcpbga.pdf` | 404 | 746 | https://www.nxp.com/docs/en/application-note/AN13656.pdf | fetch failed or blocked |
| `packaging/semco_fcbga_page.html` | 000 | 0 | https://www.sem.samsung.com/global/product/substrate/package-substrate/fcbga.do | fetch failed or blocked |
| `packaging/toppan_fcbga_page.html` | 200 | 17000 | https://www.toppan.com/en/electronics/package/fc-bga/ | not needed for a cited fact |
| `hbm/trendforce_fms2025_hbm_process.pdf` | 000 | 0 | https://files.futurememorystorage.com/proceedings/2025/20250807_DRAM-301-1_Tom-Hsu.pdf | fetch failed or blocked |
| `packaging/intel_foundry_dc_library.html` | 403 | 499 | https://www.intel.com/content/www/us/en/foundry/library/advanced-process-technologies-for-data-center.html | fetch failed or blocked |
| `packaging/altera_pkgds_2011.pdf` | 403 | 111 | https://cdrdv2-public.intel.com/653885/pkgds.pdf | fetch failed or blocked |
| `hbm/trendforce_fms2025_hbm_process_retry.pdf` | 000 | 0 | https://files.futurememorystorage.com/proceedings/2025/20250807_DRAM-301-1_Tom-Hsu.pdf | fetch failed or blocked |
| `packaging/s2_api_tsmc_icap_iedm2019.html` | 429 | 174 | https://api.semanticscholar.org/graph/v1/paper/9355d527c7d9d501c5ec7bd8e88dd26c084c8a68?fields=title,abstract,year,venue,authors,externalIds | fetch failed or blocked |
| `packaging/s2_page_tsmc_icap_iedm2019.html` | 202 | 0 | https://www.semanticscholar.org/paper/Integrated-Deep-Trench-Capacitor-in-Si-Interposer-Hou-Wu/9355d527c7d9d501c5ec7bd8e88dd26c084c8a68 | fetch failed or blocked |

## Page renders (visual evidence)

- `evidence/hbm/renders/micron_hbm3e_brief_p2.png`
- `evidence/hbm/renders/skhynix_hc28_p18.png`
- `evidence/hbm/renders/skhynix_hc28_p8.png`
- `evidence/hbm/renders/skhynix_hc28_p9.png`
- `evidence/hbm/renders/ucie_buss25_p7.png`
- `evidence/packaging/renders/microchip_fcbga196_p2.png`
- `evidence/packaging/renders/renesas_alg784_p1.png`
- `evidence/packaging/renders/tsmc_hc33_p22.png`
- `evidence/packaging/renders/tsmc_hc33_p24.png`
- `evidence/packaging/renders/tsmc_hc33_p30.png`
- `evidence/packaging/renders/tsmc_hc33_p36.png`
- `evidence/packaging/renders/xilinx_cpmt1104b_p15.png`
- `evidence/products/renders/amd_hc2024_p3.png`
- `evidence/products/renders/amd_hc2024_p4.png`
- `evidence/products/renders/huawei_hc31_p33.png`
- `evidence/products/renders/huawei_hc31_p37.png`
- `evidence/products/renders/huawei_hc31_p38.png`

## Repo excerpts (trusted, our own code)

- `evidence/repo/docs_sentilab_references_README.md.numbered.txt`
- `evidence/repo/sundai_hotspot_UPSTREAM_COMMIT.numbered.txt`
- `evidence/repo/sundai_hotspot__temperature_grid.c.excerpts.numbered.txt`
- `evidence/repo/sundai_hotspot_package.config.numbered.txt`
- `evidence/repo/sundai_hotspot_tap_oracle.py.numbered.txt`
- `evidence/repo/sundai_hotspot_tap_oracle_worker.py.numbered.txt`
- `evidence/repo/sundai_hotspot_tap_references.py.numbered.txt`
- `evidence/repo/sundai_tap_README.md.numbered.txt`
- `evidence/repo/sundai_tap_UPSTREAM_COMMIT.numbered.txt`
- `evidence/repo/sundai_tap_configs_sys_ascend910.cfg.numbered.txt`
- `evidence/repo/sundai_tap_configs_sys_ascend910_45mm.cfg.numbered.txt`
- `evidence/repo/sundai_tap_configs_sys_micro150.cfg.numbered.txt`
- `evidence/repo/sundai_tap_configs_sys_micro150_45mm.cfg.numbered.txt`
- `evidence/repo/sundai_tap_configs_sys_multigpu.cfg.numbered.txt`
- `evidence/repo/sundai_tap_passive_interposer.py.numbered.txt`
- `evidence/repo/sundai_tap_util_fill_space.py.numbered.txt`
- `evidence/repo/sundai_tap_util_hotspot.config.numbered.txt`
- `evidence/repo/web_public_temperature-label.mjs.numbered.txt`

## Tools (outside evidence/)

`tools/` holds the scripts used: `fetch.sh`, `html2txt.py`, `render_page.py`, `build_facts.py`, `verify_facts.py`, `build_parts.py` and `build_sources_md.py`.

To re-verify:

```
python -I tools/verify_facts.py evidence
sha256sum -c SHA256SUMS
```
