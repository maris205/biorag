可以，就用 **OmniGene-4-CPT-v2-merged** 提向量，不用 SFT 版。这个选择很合理：

> **CPT 模型负责构建 sequence/text embedding；SFT / Gemma 4 agent 负责问答、路由、总结。**

你这个方向可以定义成：

> **Open-Rosalind Local Bio-KB / Hybrid BioRAG：把经典生物检索、OmniGene 向量 RAG、DRAG/GraphRAG 统一到一个本地生命科学知识库里。**

OmniGene-4-CPT-v2-merged 的模型卡里也正好说明它是一个已合并的 BF16 CPT 模型，基座是 Gemma-4-26B-A4B-Instruct MoE，128 experts、top-8 routing，并且已经加入 DNA、protein、3Di、DSSP 等生物 token，CPT 数据包括 DNA、protein、OpenWebText、structure 等混合语料。这个版本比 SFT 版更适合做表征和检索向量。([Hugging Face][1])

---

# 1. MVP5 总体目标

MVP5 可以叫：

```text
Open-Rosalind Local Bio-KB Standard
```

目标不是做一个普通 PDF RAG，而是做一个 **本地化生命科学知识库层**：

```text
local biological data
+ classical retrieval
+ OmniGene embedding RAG
+ DRAG / GraphRAG
+ Open-Rosalind agent workflow
```

最终在 agent 中形成：

```text
User query
→ Local Bio-KB Router
→ SQL / FTS / BLAST / Vector RAG / DRAG
→ evidence aggregation
→ Gemma 4 / Open-Rosalind summary
→ trace + confidence
```

你的思路最重要的点是：

> **把各类序列、文献、注释、通路、变异、问题统一到一个本地库里。**

这和普通方法不一样。普通方法往往是：

```text
文本库一套 RAG
序列库一套 BLAST
注释库一套 SQL
知识图谱又一套 graph DB
```

你这里可以做成：

> **一个逻辑统一的 Local Bio-KB，多种索引只是它的不同视图。**

也就是说，物理上可以有 SQLite / BLAST / vector index / graph index，但用户和 agent 看到的是一个统一知识库。

---

# 2. 数据集方案

你已经有：

```text
dnagpt/open-rosalind-kb-standard
```

这个数据集可以作为 MVP5 的 Standard 版本基础。

你当前描述的 Standard raw bundle 大约 60GB，已经包含：

```text
UniProt Swiss-Prot
NCBI Gene
HGNC
Gene Ontology
Reactome
ClinVar
Ensembl human
PubMed baseline
Swiss-Prot BLAST FASTA
```

这个规模非常适合作为 Standard：

```text
Basic: <1GB
Standard: 30–80GB
Full: ~500GB
```

MVP5 建议只做 Standard，不要现在冲 Full。

---

## 2.1 Standard 数据源分层

建议把数据源统一分成 6 类：

### A. Entity annotation data

```text
HGNC
NCBI Gene
UniProt Swiss-Prot
Ensembl human
```

用途：

```text
gene/protein lookup
alias normalization
cross-reference mapping
gene → protein
gene → transcript
protein → sequence
```

---

### B. Functional knowledge data

```text
GO
GOA human
Reactome
```

用途：

```text
gene/protein → function
gene/protein → pathway
pathway → genes/proteins
GO term explanation
```

---

### C. Clinical / variant data

```text
ClinVar
gene-condition summaries
variant summaries
```

用途：

```text
gene → clinical conditions
variant → clinical significance
mutation query support
```

---

### D. Literature data

```text
PubMed baseline
future: PMC OA / local PDFs
```

用途：

```text
paper retrieval
gene/protein literature evidence
sequence-related paper retrieval
```

---

### E. Sequence data

```text
Swiss-Prot FASTA
Ensembl peptide FASTA
cDNA FASTA
custom FASTA
```

用途：

```text
BLAST search
sequence embedding
sequence → protein/gene annotation
sequence → literature/pathway evidence
```

---

### F. User / lab extension data

后续本地部署时可以加：

```text
private FASTA
internal PDFs
lab notes
custom annotations
experimental sequence sets
```

这个就是你 local-first 的产品特色。

---

# 3. 索引构建方案

MVP5 不要只做一种索引。建议分成四层：

```text
1. SQL / FTS classical index
2. BLAST / sequence similarity index
3. OmniGene vector RAG index
4. DRAG / GraphRAG graph index
```

但注意：它们都挂在同一个 Local Bio-KB schema 下。

---

# 4. 统一 Local Bio-KB Schema

建议先设计一个统一实体表。

## 4.1 Core tables

```sql
entities(
  entity_id,
  entity_type,
  name,
  canonical_id,
  source,
  description,
  organism,
  metadata_json
)
```

entity_type 包括：

```text
gene
protein
sequence
paper
pathway
go_term
variant
disease
organism
compound 后续可加
```

---

## 4.2 Alias / xref table

```sql
aliases(
  entity_id,
  alias,
  alias_type,
  source
)
```

用途：

```text
BRCA1
BRCC1
RNF53
UniProt accession
NCBI Gene ID
Ensembl ID
HGNC ID
```

---

## 4.3 Text chunks

```sql
text_chunks(
  chunk_id,
  entity_id,
  source,
  title,
  text,
  chunk_type,
  year,
  pmid,
  metadata_json
)
```

用于 PubMed、UniProt function、Reactome description、GO definition 等文本。

---

## 4.4 Sequence records

```sql
sequences(
  sequence_id,
  entity_id,
  sequence_type,
  sequence,
  sequence_hash,
  length,
  alphabet,
  source,
  accession,
  metadata_json
)
```

sequence_type：

```text
protein
dna
rna
peptide_fragment
cdna
3di
dssp
```

---

## 4.5 Edges / graph relations

```sql
relations(
  source_entity_id,
  relation_type,
  target_entity_id,
  evidence_id,
  source,
  confidence,
  metadata_json
)
```

relation_type 例如：

```text
encodes
has_protein
has_sequence
has_function
participates_in_pathway
annotated_with_go
mentioned_in_paper
associated_with_disease
has_variant
similar_to
ortholog_of
has_xref
```

---

# 5. Classical Index 构建

## 5.1 SQLite / PostgreSQL + FTS5

第一版继续用 SQLite FTS5 就够。

建议建这些 FTS 表：

```text
gene_fts
protein_fts
pathway_fts
go_fts
clinvar_fts
pubmed_fts
uniprot_fts
```

支持：

```text
BRCA1
DNA repair
homologous recombination
apoptosis
MAPK pathway
EGFR resistance
KRAS G12D
```

---

## 5.2 BLAST / DIAMOND / MMseqs2

第一版：

```text
BLAST Swiss-Prot DB
```

后续：

```text
DIAMOND for faster protein search
MMseqs2 for large-scale sequence search
minimap2 for DNA/RNA mapping
```

MVP5 当前可以先保持 BLAST，因为你已经 smoke test 成功。

---

# 6. OmniGene Vector RAG 索引

## 6.1 模型选择

使用：

```text
dnagpt/OmniGene-4-CPT-v2-merged
```

作为 embedding 提取模型。

原因：

```text
CPT 后模型学到 DNA / protein / structure / text 的领域表示；
SFT 后模型更偏 instruction following，不一定适合作 embedding。
```

模型卡也说明这个 merged CPT 模型可直接加载，不需要再依赖 base Gemma-4 模型；BF16 约 50GB，4-bit 量化可降低显存占用。([Hugging Face][1])

---

## 6.2 向量对象类型

建议统一提 5 类向量：

```text
1. query embedding
2. paper / abstract embedding
3. gene/protein description embedding
4. sequence embedding
5. pathway / GO / variant summary embedding
```

---

## 6.3 Text embedding 输入模板

不要直接把原始文本丢进去，最好统一模板：

```text
[TYPE=paper]
Title: ...
Abstract: ...
Keywords: ...
```

```text
[TYPE=protein]
Gene: BRCA1
Protein: Breast cancer type 1 susceptibility protein
Function: ...
Organism: Homo sapiens
```

```text
[TYPE=pathway]
Pathway: Homologous recombination repair
Description: ...
Participants: BRCA1, BRCA2, RAD51...
```

这样模型知道对象类型。

---

## 6.4 Sequence embedding 输入模板

序列更关键，要统一格式。

蛋白：

```text
[TYPE=protein_sequence]
Accession: P38398
Gene: BRCA1
Organism: Homo sapiens
Sequence:
M...
```

短肽：

```text
[TYPE=peptide_fragment]
Sequence:
MVKVGVNGFGRIGRLVTRA
```

DNA：

```text
[TYPE=dna_sequence]
Organism: Homo sapiens
Sequence:
ATG...
```

3Di / DSSP：

```text
[TYPE=structure_sequence]
3Di:
...
DSSP:
...
```

这样后面可以比较：

```text
raw sequence embedding
vs
typed sequence embedding
vs
sequence + metadata embedding
```

---

## 6.5 Pooling 方法

第一版建议简单稳定：

```text
last hidden state mean pooling over non-padding tokens
```

或者：

```text
EOS token pooling
```

推荐先做两个版本比较：

```text
mean pooling
EOS pooling
```

如果有时间，再加一个 projection head / contrastive tuning。

---

## 6.6 Vector DB

MVP5 推荐：

```text
FAISS
```

因为简单、快、适合本地。

索引可以分几类：

```text
faiss_text.index
faiss_sequence.index
faiss_entity.index
faiss_all.index
```

但逻辑上仍然挂在统一 KB 下。

---

# 7. DRAG / GraphRAG 方案

你这里说的 DRAG，我建议定义成：

> **Domain Retrieval-Augmented Graph for Biology**

也就是面向生物领域的图增强检索。

它和普通 GraphRAG 的区别是：

```text
不是只从文本抽实体关系，
而是把生物数据库里的天然关系、序列相似关系、文献证据关系全部图谱化。
```

---

## 7.1 知识图谱是什么？

这个图谱不是“模型幻想出来的图”，而是由本地 KB 中的结构化关系生成。

节点包括：

```text
Gene
Protein
Sequence
Paper
Pathway
GO Term
Variant
Disease / Condition
Organism
Database Entry
```

边包括：

```text
gene encodes protein
protein has sequence
protein annotated with GO term
protein participates in pathway
gene mentioned in paper
protein mentioned in paper
variant located in gene/protein
variant associated with condition
sequence similar to sequence
paper supports relation
```

---

## 7.2 序列本身生成的知识图谱是什么意思？

这个问题很关键。

序列图谱不是说“把 ACGT 每个碱基都画成节点”。那样没意义。

更合理的是：

> **把 sequence 当成一个可检索的生物实体节点，并把它和 annotation、similarity、paper、gene/protein、domain、motif、variant 连接起来。**

例如一个 protein sequence node：

```text
Sequence: seq_abc123
Type: protein
Length: 20
Hash: ...
Source: user_query / Swiss-Prot / paper
Embedding: OmniGene vector
```

它可以连接到：

```text
seq_abc123 --similar_to--> GAPDH Swiss-Prot sequence
seq_abc123 --belongs_to--> GAPDH-family protein
GAPDH protein --encoded_by--> GAPDH gene
GAPDH protein --annotated_with--> GO:glycolytic process
GAPDH protein --mentioned_in--> PubMed papers
GAPDH protein --participates_in--> glycolysis pathway
```

所以当用户输入：

```text
MVKVGVNGFGRIGRLVTRA
```

系统可以生成这样一条图路径：

```text
query peptide sequence
→ similar_to Swiss-Prot GAPDH-family hit
→ protein family / accession
→ gene symbol
→ GO function
→ pathway
→ literature evidence
```

这就是 **sequence-to-knowledge graph expansion**。

这是你项目非常强的特色点。

---

## 7.3 序列图谱的几类边

### A. Identity / ownership edges

```text
gene --encodes--> protein
protein --has_sequence--> sequence
transcript --has_cdna_sequence--> sequence
paper --mentions_sequence--> sequence
```

### B. Similarity edges

来自 BLAST / DIAMOND / MMseqs2：

```text
query_sequence --similar_to--> swissprot_sequence
```

metadata：

```text
pident
alignment_length
evalue
bitscore
coverage
```

### C. Embedding-neighbor edges

来自 OmniGene embedding：

```text
sequence --semantic_neighbor_of--> sequence
sequence --retrieves--> paper_chunk
sequence --similar_to_description--> protein_annotation
```

这个可以捕捉 BLAST 不擅长的语义相近关系，比如：

```text
短片段
跨模态 sequence-text
功能相近但序列不完全相似
```

### D. Functional edges

来自 UniProt / GO / Reactome：

```text
protein --has_function--> function text
protein --annotated_with--> GO term
protein --participates_in--> Reactome pathway
```

### E. Evidence edges

```text
relation --supported_by--> paper
annotation --supported_by--> database_entry
variant_claim --supported_by--> ClinVar
```

这正好服务 Open-Rosalind 的 evidence trace。

---

# 8. DRAG 检索流程

以用户输入序列为例：

```text
Input: protein sequence / peptide fragment
```

流程：

```text
1. detect sequence type
2. create query sequence node
3. BLAST against local Swiss-Prot
4. retrieve top sequence hits
5. expand graph:
   hit sequence → protein → gene → GO / pathway / papers
6. OmniGene sequence embedding search:
   query sequence → nearest sequence/text nodes
7. merge evidence
8. Gemma 4 summary
9. trace all paths
```

输出可以包含：

```text
Top similar proteins
Likely family
GO functions
Pathways
Supporting papers
BLAST evidence
Vector evidence
Graph paths
Confidence
```

---

# 9. RAG vs DRAG vs Classical 对比

你可以在论文里比较四种方法：

## A. Classical only

```text
SQL / FTS5 + BLAST
```

优势：

```text
准确、可解释、传统生信可信
```

缺点：

```text
跨模态弱、语义检索弱
```

---

## B. Vector RAG only

```text
OmniGene text/sequence embedding + FAISS
```

优势：

```text
自然语言友好
跨文本/序列可能更强
模糊查询能力好
```

缺点：

```text
可解释性弱
可能检索到语义相近但生物证据不强的结果
```

---

## C. DRAG / GraphRAG

```text
entity graph + relation expansion + evidence paths
```

优势：

```text
多跳解释强
能把 gene/protein/sequence/paper/pathway 串起来
输出路径可审计
```

缺点：

```text
依赖图谱覆盖率
构建复杂
```

---

## D. Hybrid BioRAG

```text
SQL + BLAST + Vector RAG + DRAG
```

优势：

```text
最适合 Open-Rosalind
本地优先
证据完整
适合多模态生物检索
```

这应该是你的主系统。

---

# 10. “统一成一个库”的论文亮点

你说得对，这个可以作为项目特色：

> **各种序列和问题都统一到一个 Local Bio-KB，而不是让用户面对多套割裂索引。**

但建议表述更准确：

```text
Open-Rosalind uses one logical local knowledge base with multiple retrieval views.
```

中文：

```text
Open-Rosalind 使用一个逻辑统一的本地知识库，并为不同生物对象提供多种检索视图。
```

底层仍然可以有：

```text
SQL view
FTS view
BLAST view
vector view
graph view
```

但 agent 看到的是统一接口：

```text
local.bio_search(query, mode="auto")
```

这比传统方式好：

```text
传统方法：
用户/系统要知道什么时候用 SQL、什么时候用 BLAST、什么时候用 RAG。

Open-Rosalind：
agent 自动选择或融合检索方法，并记录 trace。
```

---

# 11. 索引构建流程

## 11.1 下载数据集

```bash
huggingface-cli download dnagpt/open-rosalind-kb-standard \
  --repo-type dataset \
  --local-dir /autodl-fs/data/open-rosalind-kb/standard
```

---

## 11.2 构建 classical index

```bash
python -m open_rosalind.localdb.build_standard_index \
  --root /autodl-fs/data/open-rosalind-kb/standard \
  --limit hgnc=50000 \
  --limit reactome_human=5000 \
  --limit go_terms=5000 \
  --limit clinvar_gene=5000 \
  --limit ncbi_gene_human=50000 \
  --limit clinvar_variants=100000 \
  --limit pubmed=1000000 \
  --smoke-query BRCA1 \
  --smoke-query "DNA repair"
```

建议逐步打开：

```text
ncbi_gene_human
clinvar_variants
pubmed
uniprot_parsed
```

---

## 11.3 构建 BLAST DB

```bash
makeblastdb \
  -in /autodl-fs/data/open-rosalind-kb/standard/index/blast/swissprot.fasta \
  -dbtype prot \
  -parse_seqids \
  -out /autodl-fs/data/open-rosalind-kb/standard/index/blast/swissprot
```

---

## 11.4 构建 OmniGene vector index

新增脚本：

```bash
python -m open_rosalind.localdb.build_vector_index \
  --root /autodl-fs/data/open-rosalind-kb/standard \
  --model dnagpt/OmniGene-4-CPT-v2-merged \
  --targets text,sequence,entity \
  --pooling mean \
  --dtype bf16 \
  --batch-size 8 \
  --output /autodl-fs/data/open-rosalind-kb/standard/index/vector
```

输出：

```text
vector/text.faiss
vector/sequence.faiss
vector/entity.faiss
vector/id_map.parquet
vector/manifest.json
```

---

## 11.5 构建 DRAG graph index

新增脚本：

```bash
python -m open_rosalind.localdb.build_graph_index \
  --root /autodl-fs/data/open-rosalind-kb/standard \
  --include gene,protein,sequence,paper,pathway,go,variant,disease \
  --output /autodl-fs/data/open-rosalind-kb/standard/index/graph
```

输出：

```text
graph/nodes.parquet
graph/edges.parquet
graph/entity_aliases.parquet
graph/graph.sqlite
graph/manifest.json
```

如果后续要图数据库：

```text
DuckDB / SQLite first
Neo4j optional
NetworkX for offline analysis
```

第一版 SQLite / DuckDB 就够了。

---

# 12. Agent Skill 设计

建议增加这些 local skills：

```text
local.gene_lookup
local.protein_lookup
local.pathway_lookup
local.variant_lookup
local.literature_search
local.sequence_search
local.vector_search
local.graph_expand
local.hybrid_bio_search
```

其中核心是：

```text
local.hybrid_bio_search
```

输入：

```json
{
  "query": "...",
  "query_type": "auto",
  "local_first": true,
  "fallback_public_api": true,
  "retrieval_modes": ["sql", "fts", "blast", "vector", "graph"]
}
```

输出：

```json
{
  "answer_context": [...],
  "evidence": [...],
  "retrieval_trace": [...],
  "local_coverage": 0.86,
  "fallback_used": false
}
```

---

# 13. 评测方法

## 13.1 系统对比组

建议至少 5 组：

```text
A. Public API only
UniProt / PubMed live tools

B. Local Classical
SQL / FTS5 / BLAST

C. Local Vector RAG
OmniGene vector retrieval only

D. Local DRAG
Graph expansion only

E. Local Hybrid BioRAG
SQL + FTS + BLAST + Vector + Graph

F. Local-first + Public fallback
Hybrid local first, fallback to public APIs for long-tail queries
```

---

## 13.2 任务集

建议 100–200 个任务。

### 任务 1：gene/protein lookup

```text
BRCA1, TP53, EGFR, KRAS, APOE
```

指标：

```text
Hit@k
answer accuracy
evidence correctness
```

---

### 任务 2：pathway/function lookup

```text
DNA repair
apoptosis
MAPK signaling
homologous recombination
```

指标：

```text
pathway hit@k
GO/pathway correctness
```

---

### 任务 3：variant query

```text
BRCA1 p.Lys1753Arg
KRAS G12D
EGFR L858R
TP53 R175H
```

指标：

```text
variant match rate
clinical significance correctness
evidence support rate
```

---

### 任务 4：literature retrieval

```text
BRCA1 DNA repair papers
CRISPR off-target studies
EGFR resistance mutations
```

指标：

```text
Recall@k
NDCG
citation correctness
```

---

### 任务 5：sequence similarity

```text
short peptide
full protein
ambiguous sequence
paper-extracted sequence
```

指标：

```text
BLAST hit correctness
sequence embedding neighbor correctness
family identification accuracy
```

---

### 任务 6：multi-hop agent question

例如：

```text
Given this peptide, identify likely protein family and find related functional literature.
```

评：

```text
final answer accuracy
evidence grounding
trace completeness
workflow success
```

---

## 13.3 Retrieval 指标

```text
Recall@1 / @5 / @10
MRR
NDCG@k
Hit@k
evidence precision
local coverage rate
fallback rate
latency
```

---

## 13.4 Agent 指标

```text
final answer accuracy
tool correctness
evidence grounding rate
citation correctness
trace completeness
hallucination rate
workflow success
```

---

# 14. RAG / DRAG 论文核心实验

你的论文可以围绕三个问题：

## Q1：经典方法 vs OmniGene RAG

```text
BLAST / SQL 是否仍然强于 vector RAG？
Vector RAG 在自然语言、跨模态、模糊查询上是否有优势？
```

---

## Q2：DRAG 是否提升多跳解释？

```text
Graph expansion 是否提升 gene → protein → sequence → paper → pathway 的 evidence chain？
```

---

## Q3：Hybrid 是否最适合 Bio-Agent？

```text
SQL/BLAST 保证准确性
Vector RAG 增强语义召回
DRAG 提供可解释多跳路径
Agent 汇总证据并生成 trace
```

这就是论文结论。

---

# 15. 推荐论文标题

```text
Open-Rosalind Local Bio-KB: Hybrid Classical, Neural, and Graph Retrieval for Local-First Biomedical Agents
```

或者：

```text
Hybrid BioRAG for Local Biomedical Agents: Unifying SQL, BLAST, OmniGene Embeddings, and Domain Graph Retrieval
```

更强调你的 OmniGene：

```text
OmniGene-RAG: Unified Sequence-Text Retrieval for Local-First Biomedical Agents
```

---

# 16. 一句话总结

基于你现在的 `dnagpt/open-rosalind-kb-standard` 和 `OmniGene-4-CPT-v2-merged`，MVP5 完全可以这样做：

```text
Standard Local Bio-KB
→ SQL / FTS / BLAST classical retrieval
→ OmniGene CPT sequence/text embeddings
→ vector RAG
→ DRAG / biological knowledge graph
→ hybrid local-first agent retrieval
→ BioBench-Local evaluation
```

最大的特色是：

> **不是把生物文献塞进一个向量库，而是把序列、基因、蛋白、通路、变异、文献和问题统一成一个本地生命科学知识库，并让 agent 自动选择经典检索、向量检索和图检索。**

这会成为 Open-Rosalind 很强的产品和论文特色点。

[1]: https://huggingface.co/dnagpt/OmniGene-4-CPT-v2-merged "dnagpt/OmniGene-4-CPT-v2-merged · Hugging Face"
