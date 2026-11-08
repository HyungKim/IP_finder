# 참고 문헌 (학술·1차 출처)

보고서에 인용할 수 있도록, 이 도구가 쓰는 기법마다 원 논문이나 1차 출처를 적는다. 새 기법을 넣을 때마다 여기에 한 줄을 더한다.
표기는 저자(연도), 제목, 발표처. arXiv 번호는 arxiv.org/abs/<번호>. ※ 표시는 저장소에서 확인하지 못한 세부(쪽수 등)가 있어 인용 전 원문을 한 번 더 볼 것.

## 0단계에 쓰인 기법

### 문장 임베딩과 유사도
- Chen, J., Xiao, S., Zhang, P., Luo, K., Lian, D., Liu, Z. (2024). *BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation.* arXiv:2402.03216. — 기본 임베딩 모델 bge-m3 의 논문.
- Reimers, N., Gurevych, I. (2019). *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks.* EMNLP-IJCNLP. arXiv:1908.10084. — 문장을 벡터로 바꾸고 코사인 유사도로 비교하는 방식의 대표 논문.
- Muennighoff, N., Tazi, N., Magne, L., Reimers, N. (2023). *MTEB: Massive Text Embedding Benchmark.* EACL. arXiv:2210.07316. — 임베딩 모델 비교 벤치마크. KURE 가 쓴 한국어 검색 벤치마크(MTEB-ko-retrieval)의 틀.
- 고려대학교 NLP&AI 연구실 (2024). *KURE-v1 (Korea University Retrieval Embedding).* 모델 카드: huggingface.co/nlpai-lab/KURE-v1 (MIT). ※ 별도 논문 없이 모델 카드와 벤치마크 공개. 보고서에는 모델 카드를 출처로.

### 분류기
- **proto (원형 문장 코사인, 제로샷)** — Snell, J., Swersky, K., Zemel, R. (2017). *Prototypical Networks for Few-shot Learning.* NeurIPS. arXiv:1703.05175. — '등급마다 대표 벡터(원형)를 두고 가장 가까운 등급으로' 라는 아이디어의 대표 논문. 우리 구현은 학습 없이 예시 문장의 임베딩을 원형으로 쓰는 단순판이다.
- **knn (최근접 이웃)** — Cover, T., Hart, P. (1967). *Nearest neighbor pattern classification.* IEEE Transactions on Information Theory, 13(1), 21–27. — k-NN 의 원 논문.
- **centroid (등급 평균 벡터)** — Rocchio, J. J. (1971). *Relevance Feedback in Information Retrieval.* In Salton, G. (ed.), *The SMART Retrieval System*, Prentice-Hall, 313–323. — 클래스 중심(centroid) 기반 분류의 뿌리. 텍스트 분류에서는 'Rocchio classifier' 또는 'nearest centroid' 로 불린다.
- **softmax (소프트맥스 회귀 = 다항 로지스틱 회귀)** — Bishop, C. M. (2006). *Pattern Recognition and Machine Learning.* Springer, 4.3절 (Probabilistic Discriminative Models). — 교차 엔트로피와 경사하강으로 학습하는 다항 로지스틱 회귀의 교과서 설명.
- **ovr (일대다 로지스틱)** — Rifkin, R., Klautau, A. (2004). *In Defense of One-Vs-All Classification.* Journal of Machine Learning Research, 5, 101–141. — 등급마다 이진 분류기를 두는 방식이 단순함에도 경쟁력이 있음을 보인 논문.
- **ngram (글자 n-gram + 해시)** — Cavnar, W. B., Trenkle, J. M. (1994). *N-Gram-Based Text Categorization.* Proc. SDAIR-94, 161–175. — 글자 n-gram 으로 문서를 분류하는 고전. / Weinberger, K., Dasgupta, A., Langford, J., Smola, A., Attenberg, J. (2009). *Feature Hashing for Large Scale Multitask Learning.* ICML. arXiv:0902.2206. — n-gram 을 고정 길이 벡터에 담는 해시 기법(hashing trick).
- **cue (단서어 규칙)** — 학술 출처 없음. 사람이 적은 키워드 규칙(rule-based baseline). 기준선으로만 쓴다.
- **신뢰도 통일과 과신** — Guo, C., Pleiss, G., Sun, Y., Weinberger, K. Q. (2017). *On Calibration of Modern Neural Networks.* ICML. arXiv:1706.04599. — 분류기가 내는 확률이 실제 적중률과 어긋나는(과신) 문제와 측정법. 소프트맥스 과신 경향을 설명할 때 인용.

### 측정 방법
- **층화 k 겹 교차 검증** — Kohavi, R. (1995). *A Study of Cross-Validation and Bootstrap for Accuracy Estimation and Model Selection.* IJCAI, 1137–1143. — 정확도 추정에 층화 10겹(우리는 5겹) 교차 검증을 권한 논문.
- **정밀도·재현율·F1, 거시 F1** — van Rijsbergen, C. J. (1979). *Information Retrieval* (2nd ed.). Butterworths. / Sokolova, M., Lapalme, G. (2009). *A systematic analysis of performance measures for classification tasks.* Information Processing & Management, 45(4), 427–437. — 다중 등급에서 거시 평균 F1 등 지표 정의.
- **제거 실험(ablation, 사다리)** — Meyes, R., Lu, M., de Puiseau, C. W., Meisen, T. (2019). *Ablation Studies in Artificial Neural Networks.* arXiv:1901.08644. — 구성 요소를 하나씩 빼거나 더해 기여를 재는 방법을 정리한 글. 사다리 실행(누적/단독)의 근거.
- **문장 맞추기의 유사도(difflib)** — Ratcliff, J. W., Obershelp, J. A. (1988). *Pattern Matching: the Gestalt Approach.* Dr. Dobb's Journal, July 1988. — 파이썬 difflib.SequenceMatcher 가 쓰는 알고리즘.

### 읽기(레이아웃 분석)
- Nagy, G., Seth, S. (1984). *Hierarchical representation of optically scanned documents.* Proc. 7th Int. Conf. on Pattern Recognition (ICPR), 347–349. — 재귀 X-Y cut 으로 쪽을 단·블록으로 나누는 방법. PDF 리더의 다단 분리가 이것.

## 앞 단계(3단계 LLM 2차)에 쓸 기법

- **분류기 1차 → LLM 2차 (cascade)** — Viola, P., Jones, M. (2001). *Rapid Object Detection using a Boosted Cascade of Simple Features.* CVPR. — 값싼 판정기로 거른 뒤 비싼 판정기를 쓰는 cascade 구조의 원형. / Chen, L., Zaharia, M., Zou, J. (2023). *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance.* arXiv:2305.05176. — 작은 모델에서 큰 모델로 넘기는 LLM cascade 를 다룬 논문(비용 절감 관점).
- **LLM 의 분류(프롬프트로 등급 판정)** — Brown, T. et al. (2020). *Language Models are Few-Shot Learners.* NeurIPS. arXiv:2005.14165. — 예시 몇 개(또는 없이) 지시만으로 분류하는 방식의 출발점.
- **Qwen3** — Qwen Team (2025). *Qwen3 Technical Report.* arXiv:2505.09388. — 2차 판정에 쓸 모델.

## 관련 연구 (특허·기술 문서 분류)
- Lee, J.-S., Hsiang, J. (2020). *Patent classification by fine-tuning BERT language model.* World Patent Information, 61, 101965. — 특허 문서를 BERT 로 분류한 연구. 우리 과제(보고서에서 특허 후보 문장 추출)와 가장 가까운 응용.
- ※ Laya (Convai Innovations, 2026) — 결정(판정) 전용 소형 모델. 공개 모델이며 논문은 확인하지 못함. 1차 분류기 대안으로 검토했으나 PyTorch 의존성과 약한 한국어 제로샷 성능으로 보류(`docs/stages/01-classifier.md`).

## 모델·라이브러리 라이선스 출처
- bge-m3: MIT — huggingface.co/BAAI/bge-m3 (모델 카드 `license: mit`)
- KURE-v1: MIT — huggingface.co/nlpai-lab/KURE-v1, GGUF 변환본 huggingface.co/Bingsu/KURE-v1-Q8_0-GGUF
- Ollama: MIT — github.com/ollama/ollama
- PyMuPDF: AGPL-3.0 / 상용(Artifex) 이중 라이선스 — pymupdf.readthedocs.io, artifex.com. 사내 사용 전 OSS 정책 확인.
- python-pptx: MIT. openpyxl: MIT. numpy: BSD-3. pygments(개발 도구): BSD-2.
