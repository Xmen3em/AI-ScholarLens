"""Hosted model resolution while inheriting every existing evidence guard."""

from src.exceptions import UnsupportedModelError
from src.schemas.api.rag import AskRequest
from src.services.rag.service import RAGService


class HostedRAGService(RAGService):
    def _model_for(self, request: AskRequest) -> str:
        model = request.model or self.settings.hf_default_model
        if model not in self.settings.hf_models:
            raise UnsupportedModelError("Requested generation model is not configured")
        return model
