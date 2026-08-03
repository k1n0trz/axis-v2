"""Clientes de los proveedores de IA.

DeepSeek hace el chat: es barato, sigue instrucciones bien y responde en español.
DeepInfra queda como respaldo y para lo que no tiene sentido pagarle a un modelo de
chat: embeddings y clasificacion masiva (el mapa producto -> categoria de DistriSex,
que son ~2.000 nombres una sola vez).

Los dos hablan la API de OpenAI, asi que comparten cliente.

Nada de esto bloquea el render de una pagina: el chat vive en su propio endpoint. Es
la leccion del panel de Meta, que tardaba 16 s dentro del request.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class AiProviderError(RuntimeError):
    """Fallo del proveedor. Se distingue de BudgetExceeded, que es un limite nuestro."""


class OpenAICompatibleClient:
    def __init__(self, api_key, base_url, default_model, timeout=None, max_retries=None):
        self.api_key = str(api_key or "").strip()
        self.base_url = str(base_url or "").rstrip("/")
        self.default_model = default_model
        self.timeout = int(timeout or getattr(settings, "AI_REQUEST_TIMEOUT", 60))
        self.max_retries = int(max_retries if max_retries is not None else getattr(settings, "AI_MAX_RETRIES", 2))
        self.session = requests.Session()

    @property
    def is_configured(self):
        return bool(self.api_key and self.base_url)

    def chat(self, messages, model=None, temperature=0.2, max_tokens=1200, tools=None):
        """Una respuesta de chat. Devuelve texto, uso de tokens y llamadas a herramientas."""
        if not self.is_configured:
            raise AiProviderError("El proveedor de IA no esta configurado.")

        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools

        ultimo_error = None
        # Un reintento cubre el 502/503 pasajero. Mas de dos y el usuario esta
        # esperando de gratis: mejor decirle que no se pudo.
        for intento in range(self.max_retries + 1):
            try:
                respuesta = self.session.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                ultimo_error = exc
                logger.warning("Proveedor de IA no respondio (intento %s): %s", intento + 1, exc)
                continue

            if respuesta.status_code >= 500 or respuesta.status_code == 429:
                ultimo_error = AiProviderError(f"{respuesta.status_code} del proveedor de IA")
                logger.warning("Proveedor de IA devolvio %s (intento %s)", respuesta.status_code, intento + 1)
                continue
            if not respuesta.ok:
                # 400 o 401 no se reintentan: no van a mejorar solos.
                raise AiProviderError(f"{respuesta.status_code} del proveedor de IA: {respuesta.text[:200]}")
            return self._parse(respuesta.json())

        raise AiProviderError(f"El proveedor de IA no respondio tras {self.max_retries + 1} intentos: {ultimo_error}")

    def _parse(self, data):
        opcion = ((data.get("choices") or [{}])[0]) or {}
        mensaje = opcion.get("message") or {}
        uso = data.get("usage") or {}
        return {
            "content": mensaje.get("content") or "",
            "tool_calls": mensaje.get("tool_calls") or [],
            "model": data.get("model") or self.default_model,
            "prompt_tokens": int(uso.get("prompt_tokens") or 0),
            "completion_tokens": int(uso.get("completion_tokens") or 0),
            "finish_reason": opcion.get("finish_reason") or "",
        }


def deepseek_client(reasoner=False):
    """Cliente de chat. `reasoner=True` para analisis dificil: mas lento y mas caro."""
    modelo = (
        getattr(settings, "DEEPSEEK_REASONER_MODEL", "deepseek-reasoner")
        if reasoner
        else getattr(settings, "DEEPSEEK_CHAT_MODEL", "deepseek-chat")
    )
    return OpenAICompatibleClient(
        getattr(settings, "DEEPSEEK_API_KEY", ""),
        getattr(settings, "DEEPSEEK_API_URL", "https://api.deepseek.com"),
        modelo,
    )


def deepinfra_client(model="meta-llama/Meta-Llama-3.1-8B-Instruct"):
    """Respaldo y trabajo masivo barato."""
    return OpenAICompatibleClient(
        getattr(settings, "DEEPINFRA_API_KEY", ""),
        getattr(settings, "DEEPINFRA_API_URL", "https://api.deepinfra.com/v1/openai"),
        model,
    )
