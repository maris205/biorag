# Graph Evidence Selector Evaluation

Hyperparameters are selected on a deterministic development split and frozen on the test split. The selector uses candidate rank, corpus GO frequency, and typed GO-to-PMID edges; it does not use query labels at inference time.

Development queries: `33`; test queries: `66`.

| Split | Method | Function P/R/F1/Hit | Literature P/R/F1/Hit |
|---|---|---:|---:|
| dev | rank_first | 0.079/0.177/0.103/0.212 | 0.058/0.168/0.080/0.242 |
| dev | rank_first_budget_matched | 0.101/0.149/0.113/0.212 | 0.131/0.108/0.113/0.182 |
| dev | graph_idf | 0.111/0.159/0.123/0.212 | 0.141/0.139/0.128/0.212 |
| dev | retrieval_oracle | 0.364/0.301/0.322/0.364 | 0.242/0.150/0.175/0.242 |
| test | rank_first | 0.055/0.172/0.079/0.227 | 0.044/0.123/0.058/0.258 |
| test | rank_first_budget_matched | 0.056/0.114/0.071/0.152 | 0.101/0.091/0.085/0.197 |
| test | graph_idf | 0.081/0.153/0.100/0.212 | 0.116/0.109/0.100/0.227 |
| test | retrieval_oracle | 0.515/0.394/0.431/0.515 | 0.258/0.124/0.153/0.258 |

The retrieval oracle is budget-matched and only measures whether a correct structured identifier is present in the evidence pack. It is not an executable method.
