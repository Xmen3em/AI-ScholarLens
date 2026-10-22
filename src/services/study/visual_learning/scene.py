"""Application-owned geometry; scientific direction never follows UI mirroring."""

from dataclasses import dataclass

from src.services.study.visual_learning.models import CuratedMethod, Phase, VisualError, VisualSpec
from src.services.study.visual_learning.validation import validate_spec

COLORS = {"background": "#102332", "surface": "#1d4253", "border": "#496579", "text": "#ffffff",
          "muted": "#b3c7d4", "data": "#74c7ed", "update": "#ffa65e", "preparation": "#a9b4be"}
POSITIONS = {"question": (570, 150), "document_encoder": (160, 150), "query_encoder": (570, 320),
             "index": (160, 320), "generator": (570, 490), "passages": (160, 490),
             "answer": (570, 660), "objective": (160, 660)}
PATHS = {
    "encode": [(695, 254), (695, 320)],
    "search": [(570, 372), (410, 372)],
    "retrieve": [(285, 424), (285, 490)],
    "condition": [(410, 542), (570, 542)],
    "original_input": [(820, 202), (875, 202), (875, 542), (820, 542)],
    "predict": [(695, 594), (695, 660)],
    "prepare_index": [(285, 254), (285, 320)],
    "score_target": [(695, 594), (695, 628), (285, 628), (285, 660)],
    "update_query": [(160, 712), (100, 712), (100, 272), (660, 272), (660, 320)],
    "update_generator": [(410, 712), (500, 712), (500, 568), (570, 568)],
}
LABELS = {"encode": (775, 292), "search": (490, 353), "retrieve": (375, 461),
          "condition": (490, 522), "predict": (795, 633), "prepare_index": (375, 292),
          "score_target": (485, 618), "update_query": (490, 264), "update_generator": (515, 688)}


@dataclass(frozen=True)
class SceneNode:
    id: str
    x: int
    y: int
    width: int
    height: int
    label_ar: str
    term_en: str
    status: str
    status_color: str


@dataclass(frozen=True)
class SceneEdge:
    id: str
    relation: str
    source: str
    target: str
    label_ar: str
    points: list[tuple[int, int]]
    label_position: tuple[int, int] | None
    color: str


@dataclass(frozen=True)
class Scene:
    phase: Phase
    source_sha256: str
    source_ref: str
    title: str
    subtitle: str
    footer: str
    nodes: list[SceneNode]
    edges: list[SceneEdge]
    width: int = 1000
    height: int = 860


def build_scene(spec: VisualSpec, catalog: CuratedMethod, phase: str = "inference") -> Scene:
    spec = validate_spec(spec, catalog)
    if phase not in {"inference", "training"}:
        raise VisualError("unknown_phase")
    nodes = []
    edges = []
    for node in spec.nodes:
        if node.phase not in {phase, "both"}:
            continue
        if node.id not in POSITIONS:
            raise VisualError("unsupported_layout")
        status = ""
        if phase == "training":
            status = {"fixed": "ثابت", "updated": "بيتدرّب"}.get(catalog.training_policy.get(node.id, ""), "")
        status_color = COLORS["update"] if catalog.training_policy.get(node.id) == "updated" else COLORS["muted"]
        nodes.append(SceneNode(node.id, *POSITIONS[node.id], 250, 104, node.label_ar, node.term_en, status, status_color))
    for edge in spec.edges:
        if edge.phase not in {phase, "both"}:
            continue
        if edge.id not in PATHS:
            raise VisualError("unsupported_layout")
        color = COLORS[{"parameter_update": "update", "preparation": "preparation"}.get(edge.relation, "data")]
        edges.append(SceneEdge(edge.id, edge.relation, edge.source, edge.target, edge.label_ar,
                               PATHS[edge.id], LABELS.get(edge.id), color))
    return Scene(phase="training" if phase == "training" else "inference", source_sha256=spec.source.sha256,
                 source_ref=spec.source.paper_id + " / pp. 2–4",
                 title="وقت التدريب: إيه اللي بيتحدّث؟" if phase == "training" else "وقت الاستخدام: من السؤال للناتج",
                 subtitle="أزرق: داتا • برتقالي متقطّع: تحديث • رمادي: تجهيز مسبق",
                 footer="رسم للمكونات والتحديثات؛ مش تفصيل لكل خطوات فك الترميز.", nodes=nodes, edges=edges)
