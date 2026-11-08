import numpy as np
import pytest

from ip_finder.classify import ORDER, REGISTRY, Batch, available_names, build, load_classifier, load_file, load_prototypes
from ip_finder.classify.cv import out_of_fold_predict, stratified_folds
from ip_finder.classify.features import ngram_matrix, with_cues
from ip_finder.config import Config
from ip_finder.cues import FEATURE_NAMES
from ip_finder.prep.page_type import page_type


def _synthetic(n_per=20, dim=16, seed=0):
    rng = np.random.default_rng(seed)
    labels = ["A", "B", "C", "D", "X"]
    centers = rng.normal(size=(5, dim))
    X, y, texts = [], [], []
    for i, lab in enumerate(labels):
        for j in range(n_per):
            X.append(centers[i] + 0.3 * rng.normal(size=dim))
            y.append(lab)
            texts.append({"A": "접착제를 변경하여 적용", "B": "수율 15% 향상", "C": "응력 발생 원인", "D": "적용 예정 계획", "X": "일정 비용 담당"}[lab] + f" {j}")
    return Batch(texts, np.asarray(X, dtype=np.float32), ["general"] * len(y)), y


def test_page_type():
    assert page_type("원인 분석")[0] == "problem"
    assert page_type("검증 결과")[0] == "result"
    assert page_type("문제점 및 개선 방안") == ("general", None)      # 유형이 섞이면 힌트 없음


def test_registry_has_seven_classifiers():
    assert ORDER == ["proto", "knn", "centroid", "softmax", "ovr", "cue", "ngram"]
    assert [n for n in ORDER if REGISTRY[n].baseline] == ["cue", "ngram"]                 # 비교 기준선 둘
    assert available_names(Config()) == ORDER and available_names(Config(baseline_classifiers=False)) == ["proto", "knn", "centroid", "softmax", "ovr"]
    assert {n: (c.trainable, c.needs_embedding) for n, c in REGISTRY.items()} == {
        "proto": (False, True), "knn": (True, True), "centroid": (True, True), "softmax": (True, True), "ovr": (True, True),
        "cue": (False, False), "ngram": (True, False)}


def test_zero_shot_with_fake_embedder(fake_embedder):
    clf = build("proto", Config())
    clf.prepare(fake_embedder)
    texts = ["접착제를 저탄성 실리콘계로 변경하여 응력 저감", "조립 수율 92.1% → 97.8%로 향상", "3분기 파일럿 라인 적용 일정 조정", "차기 모델에 신규 방식 적용 예정"]
    preds = clf.predict(Batch(texts, fake_embedder.embed(texts)))
    assert [p.label for p in preds][:2] == ["A", "B"]
    assert all(0.65 <= p.confidence <= 0.9 for p in preds) and set(preds[0].scores) == {"A", "B", "C", "D", "X"}
    assert len(load_prototypes()["A"]) >= 5


def test_cue_rules():
    clf = build("cue")
    preds = clf.predict(Batch(["접착제를 변경하여 응력 저감", "수율 15% 향상", "진동으로 체결부가 풀리는 현상 발생", "차기 모델 적용 예정", "설비 투자 비용 2억 원", "그냥 문장"]))
    assert [p.label for p in preds] == ["A", "B", "C", "D", "X", "X"]
    assert preds[0].confidence == 0.7 and preds[-1].confidence == 0.55


@pytest.mark.parametrize("name", ["knn", "centroid", "softmax", "ovr", "ngram"])
def test_trainable_classifiers_fit_predict_roundtrip(name, tmp_path):
    batch, y = _synthetic()
    clf = build(name, Config(knn_k=3))
    clf.fit(batch, y)
    preds = clf.predict(batch)
    acc = sum(p.label == g for p, g in zip(preds, y)) / len(y)
    assert acc > 0.9 and all(0.0 <= p.confidence <= 1.0 for p in preds) and clf.labels == ["A", "B", "C", "D", "X"]
    clf.meta = {"embed_model": "fake-embed", "n": len(y)}
    path = clf.save(tmp_path / f"{name}.npz")
    loaded = load_file(path, Config(knn_k=3))
    assert loaded.name == name and loaded.labels == clf.labels and loaded.meta["n"] == len(y)
    again = loaded.predict(batch.subset([0, 25, 50]))
    assert [p.label for p in again] == [preds[0].label, preds[25].label, preds[50].label]
    assert "학습" in loaded.describe()


def test_cross_validation_helpers():
    batch, y = _synthetic(n_per=10)
    folds = stratified_folds(y, k=5, seed=1)
    assert len(folds) == 5 and sorted(i for f in folds for i in f) == list(range(len(y)))
    assert all(len({y[i] for i in f}) == 5 for f in folds)                 # 층화: 겹마다 등급 다섯 개
    preds = out_of_fold_predict(build("centroid"), batch, y, k=5)
    assert all(p is not None for p in preds) and sum(p.label == g for p, g in zip(preds, y)) / len(y) > 0.8


def test_feature_builders():
    X = with_cues(np.zeros((2, 4), np.float32), ["접착제 변경", "일정 조정"], ["means", "general"])
    assert X.shape == (2, 4 + len(FEATURE_NAMES))
    N = ngram_matrix(["접착제 변경", "접착제 변경", "완전히 다른 글"])
    assert N.shape[0] == 3 and np.allclose(N[0], N[1]) and float(N[0] @ N[2]) < 0.5 and abs(float(np.linalg.norm(N[0])) - 1.0) < 1e-5


def test_load_classifier_checks_embed_model(tmp_path, fake_embedder):
    batch, y = _synthetic()
    cfg = Config(classifier="knn", classifier_dir=str(tmp_path), embed_model="fake-embed")
    clf = build("knn", cfg)
    clf.fit(batch, y)
    clf.meta = {"embed_model": "other-model"}
    clf.save(cfg.classifier_file())
    with pytest.raises(ValueError):
        load_classifier(cfg, fake_embedder)
    clf.meta = {"embed_model": "fake-embed"}
    clf.save(cfg.classifier_file())
    assert load_classifier(cfg, fake_embedder).name == "knn"
    cfg.classifier = "proto"
    assert load_classifier(cfg, fake_embedder).P is not None
