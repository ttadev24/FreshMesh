# Third-party notices and template sources

The root [GPL-3.0-only license](LICENSE) applies to original FreshMesh code. It does not replace licenses, attribution requirements, or service terms belonging to upstream projects and datasets. This is a source guide, not an exhaustive dependency license audit.

## External solver

`routing/routing-PL` is a Git submodule from [chauanphu/routing-PL](https://github.com/chauanphu/routing-PL), pinned to `32488cef9c13466133242729cf4300db6abd3a2a` when these notices were written.

The upstream Git tree at that revision contained no file with `LICENSE` or `COPYING` in its path when checked on 2026-10-17. Its redistribution rights have therefore **not been established here**. Public availability is not a license grant. Obtain or verify upstream permission before redistributing that solver or a container image containing it. FreshMesh's root license cannot grant rights to that upstream code.

## Data and services

| Material | Source / terms recorded by the project | Notes |
| --- | --- | --- |
| OpenStreetMap locations and derived geographic databases | [© OpenStreetMap contributors, ODbL 1.0](https://www.openstreetmap.org/copyright) | Preserve attribution and applicable database obligations, including for committed geographic snapshots. |
| Open-Meteo weather | [Historical weather documentation](https://open-meteo.com/en/docs/historical-weather-api), CC BY 4.0 data | Data licensing and [API service terms](https://open-meteo.com/en/terms) are distinct. |
| OSRM detour reference | [OSRM demo-server policy](https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server), OSM-derived output | Used to evaluate a distance assumption; respect server usage restrictions. |
| FreshRetailNet-50K | [Dingdong-Inc/FreshRetailNet-50K](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K), CC BY 4.0 | Separate validation data; retain dataset attribution and revision information. |
| NSO/GSO reference snapshot | [Third-party compilation](https://huggingface.co/datasets/letrinhan/vn-provinces-trade-tourism-transport-master) | The recorded dataset card says `other` without explicit terms. Redistribution rights are not established by this document. |
| Vietnamese holiday references | Source documents linked in `data_real/holidays_vn.json` | Preserve provenance; see the registry for how dates were obtained. |
| VietMap maps and route geometry | [VietMap](https://maps.vietmap.vn/docs/) | Provider terms apply; storage and redistribution rights have not been established by this project. |
| Claude / Jev integrations | Anthropic / OpenRouter and the respective model providers | Account, model, and API terms apply separately. Credentials and service access are not included. |

The committed AI-generated parameter files and prompt records describe how the synthetic demo was made. They are estimates, not measured transactions or endorsements by the providers. Original project-authored materials are covered by the project license to the extent the contributors hold the relevant rights; embedded third-party content retains its terms.

The detailed source registry is in [provenance/registry_defaults.json](provenance/registry_defaults.json); the recorded extraction history, dates, attribution, and limitations are in [data provenance](docs/data-provenance.md). Dependency versions are recorded in `uv.lock` and `web/package-lock.json`; consult each package's license before redistribution. In particular, the existing registry identifies `lunardate` as GPL-3.0-or-later.

## Standard documents

The license was downloaded from GitHub's Choose a License repository, with website metadata removed and the license body retained. The Contributor Covenant was downloaded from its upstream GitHub repository, with website metadata removed and the reporting contact customized.

Pinned source URLs:
- `LICENSE`: https://raw.githubusercontent.com/github/choosealicense.com/f66c5dd01866041688edd87f658b6d5ac3304f1b/_licenses/gpl-3.0.txt
- `CODE_OF_CONDUCT.md`: https://raw.githubusercontent.com/EthicalSource/contributor_covenant/7255a28d23d5bc296de2e4e4e9bb5ee1126f1345/content/version/2/1/code_of_conduct.md

The Contributor Covenant 2.1 text is attributed within [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and is available under [CC BY 4.0](https://www.contributor-covenant.org/faq/). It retains its own terms. The project-specific contribution guide, support guide, security policy, and Issue/PR templates were written for the actual FreshMesh workflow.

## Documentation artwork

[docs/assets/freshmesh-banner.png](docs/assets/freshmesh-banner.png) was generated for this repository using the built-in image-generation tool. It is a conceptual illustration, not a screenshot or measured architectural diagram. The prompt and provenance are recorded in [docs/assets/README.md](docs/assets/README.md).
