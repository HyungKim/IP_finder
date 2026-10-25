import numpy as np

from ip_finder.classify import TrainedClassifier, ZeroShotClassifier, build_features, cross_validate, load_prototypes
from ip_finder.cues import FEATURE_NAMES
from ip_finder.prep.page_type import page_type


def test_page_type():
    assert page_type("원인 분석")[0] == "problem"
    assert page_type("검증 결과")[0] == "result"
    assert page_type("개선안 1: 패키지 접착 구조 변경")[0] == "means"
    assert page_type("향후 계획")[0] == "plan"
    assert page_type("문제점 및 개선 방안") == ("general", None)      # 유형이 섞이면 힌트 없음
    assert page_type("PS-200 보고") == ("general", None)


def test_zero_shot_with_fake_embedder(fake_embedder):
    clf = ZeroShotClassifier(fake_embedder, load_prototypes())
    texts = ["접착제를 저탄성 실리콘계로 변경하여 응력 저감", "조립 수율 92.1% → 97.8%로 향상",
             "3분기 파일럿 라인 적용 일정 조정", "차기 모델에 신규 방식 적용 예정"]
    preds = clf.predict(fake_embedder.embed(texts), texts, ["general"] * 4)
    assert [p.label for p in preds][:2] == ["A", "B"]
    assert all(0.0 <= p.confidence <= 1.0 for p in preds)
    assert set(preds[0].scores) == {"A", "B", "C", "D", "X"}


def test_trained_classifier_roundtrip(tmp_path):
    rng = np.random.default_rng(0)
    labels = ["A", "B", "C", "D", "X"]
    centers = rng.normal(size=(5, 8))
    X, y = [], []
    for i, lab in enumerate(labels):
        for _ in range(20):
            X.append(centers[i] + 0.3 * rng.normal(size=8))
            y.append(lab)
    X = np.asarray(X, dtype=np.float32)
    clf = TrainedClassifier.train(X, y, meta={"embed_model": "fake-embed"})
    acc = sum(clf._proba(X).argmax(axis=1)[i] == labels.index(y[i]) for i in range(len(y))) / len(y)
    assert acc > 0.95
    assert 0.5 < cross_validate(X, y) <= 1.0
    path = tmp_path / "clf.npz"
    clf.save(path)
    loaded = TrainedClassifier.load(path)
    assert loaded.labels == labels and loaded.meta["embed_model"] == "fake-embed"
    np.testing.assert_allclose(loaded._proba(X[:3]), clf._proba(X[:3]), rtol=1e-5)


def test_build_features_shape():
    X = build_features([[0.1] * 4, [0.2] * 4], ["접착제 변경", "일정 조정"], ["means", "general"])
    assert X.shape == (2, 4 + len(FEATURE_NAMES))
