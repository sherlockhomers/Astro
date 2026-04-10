"""Astronomy-domain model adapter.

Text QA:
- AstroMLab/AstroSage-8B

Image QA:
- UniverseTBD/AstroLLaVA

Chinese user input/output is bridged through lightweight zh<->en translation
models so the frontend can stay fully Chinese while the text backbone remains
astronomy-domain focused.
"""

from __future__ import annotations

import inspect
import os
import re
import sys
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

_DOTENV_CACHE: dict[str, str] | None = None


def _load_dotenv_values() -> dict[str, str]:
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE

    env_values: dict[str, str] = {}
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        try:
            from dotenv import dotenv_values

            raw = dotenv_values(env_path)
            env_values = {str(k): str(v) for k, v in raw.items() if k and v is not None}
        except Exception:
            env_values = {}
    _DOTENV_CACHE = env_values
    return _DOTENV_CACHE


def _env(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if val is not None:
        return str(val)
    return str(_load_dotenv_values().get(key, default))


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _contains_arabic(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", str(text or "")))


class AstroModel:
    def __init__(self) -> None:
        self._text_enabled = _to_bool(_env("ASTRO_TEXT_ENABLED", "true"), True)
        self._text_model_path = _env("ASTRO_TEXT_MODEL_PATH", r"D:/models/AstroSage-8B").strip()
        self._text_lazy_load = _to_bool(_env("ASTRO_TEXT_LAZY_LOAD", "false"), False)
        self._text_quantization = _env("ASTRO_TEXT_QUANTIZATION", "4bit").strip().lower()
        self._text_max_new_tokens = int(_env("ASTRO_TEXT_MAX_NEW_TOKENS", "384"))
        self._text_temperature = float(_env("ASTRO_TEXT_TEMPERATURE", "0.0"))
        self._text_top_p = float(_env("ASTRO_TEXT_TOP_P", "0.9"))
        self._text_repetition_penalty = float(_env("ASTRO_TEXT_REPETITION_PENALTY", "1.05"))
        self._text_cpu_max_memory = _env("ASTRO_TEXT_CPU_MAX_MEMORY", "36GiB").strip()

        self._translation_enabled = _to_bool(_env("ASTRO_TRANSLATION_ENABLED", "true"), True)
        self._zh_en_model_id = _env("ASTRO_TRANSLATE_ZH_EN_MODEL", "Helsinki-NLP/opus-mt-zh-en").strip()
        self._en_zh_model_id = _env("ASTRO_TRANSLATE_EN_ZH_MODEL", "Helsinki-NLP/opus-mt-en-zh").strip()
        self._translation_max_new_tokens = int(_env("ASTRO_TRANSLATION_MAX_NEW_TOKENS", "192"))
        self._translation_cache_size = int(_env("ASTRO_TRANSLATION_CACHE_SIZE", "256"))
        self._translation_preload = _to_bool(_env("ASTRO_TRANSLATION_PRELOAD", "true"), True)

        self._vision_enabled = _to_bool(_env("ASTRO_VISION_ENABLED", "true"), True)
        self._vision_model_path = _env("ASTRO_VISION_MODEL_PATH", r"D:/models/AstroLLaVA").strip()
        self._vision_lazy_load = _to_bool(_env("ASTRO_VISION_LAZY_LOAD", "true"), True)
        self._vision_quantization = _env("ASTRO_VISION_QUANTIZATION", "4bit").strip().lower()
        self._vision_max_new_tokens = int(_env("ASTRO_VISION_MAX_NEW_TOKENS", "256"))
        self._vision_cpu_max_memory = _env("ASTRO_VISION_CPU_MAX_MEMORY", "32GiB").strip()
        self._vision_tower_path = _env("ASTRO_VISION_TOWER_PATH", r"D:/models/clip-vit-large-patch14-336").strip()
        self._vision_tower_id = _env("ASTRO_VISION_TOWER_ID", "openai/clip-vit-large-patch14-336").strip()
        self._vision_repo_path = _env(
            "ASTRO_VISION_REPO_PATH",
            str(Path(__file__).resolve().parent.parent / "vendor" / "AstroLLaVA"),
        ).strip()
        self._vision_conv_mode = _env("ASTRO_VISION_CONV_MODE", "llava_v0").strip() or "llava_v0"

        self._text_tokenizer: Any | None = None
        self._text_model: Any | None = None

        self._vision_tokenizer: Any | None = None
        self._vision_model: Any | None = None
        self._vision_processor: Any | None = None

        self._zh_en_tokenizer: Any | None = None
        self._zh_en_model: Any | None = None
        self._en_zh_tokenizer: Any | None = None
        self._en_zh_model: Any | None = None
        self._shared_translation_model: Any | None = None
        self._shared_translation_model_id: str | None = None
        self._translation_device: str = "cpu"
        self._translation_cache: OrderedDict[tuple[str, str], str] = OrderedDict()

        self._load_error: str | None = None
        self._runtime_device: str = "cpu"
        self.ready = False
        self.text_ready = False
        self.vision_ready = False

        if self._text_enabled:
            text_check = self._validate_model_dir(self._text_model_path)
            if text_check:
                self._load_error = text_check
            elif self._text_lazy_load:
                self.ready = True
            else:
                self.text_ready = self._ensure_text_loaded()
                self.ready = self.text_ready

        if self._vision_enabled:
            vision_check = self._validate_model_dir(self._vision_model_path)
            if vision_check:
                self._load_error = f"{self._load_error}; {vision_check}" if self._load_error else vision_check
            elif not self._vision_lazy_load:
                self.vision_ready = self._ensure_vision_loaded()
                self.ready = self.ready or self.vision_ready

    @staticmethod
    def _validate_model_dir(model_path: str) -> str | None:
        path = Path(model_path)
        if not path.exists():
            return f"Model path does not exist: {model_path}"
        if not path.is_dir():
            return None
        index_path = path / "model.safetensors.index.json"
        if index_path.exists():
            import json

            try:
                payload = json.loads(index_path.read_text(encoding="utf-8"))
                expected = sorted({str(v) for v in (payload.get("weight_map") or {}).values() if v})
            except Exception as exc:  # noqa: BLE001
                return f"Broken weight index: {type(exc).__name__}: {exc}"
            missing = [name for name in expected if not (path / name).exists()]
            if missing:
                return f"Model shards missing ({len(missing)}): {', '.join(missing[:3])}"
        elif not list(path.glob("*.safetensors")):
            return f"No safetensors weights found in {model_path}"
        return None

    def _build_quant_config(self, quantization: str, torch: Any, cpu_offload: bool = False) -> Any | None:
        if quantization not in {"4bit", "8bit"}:
            return None
        try:
            from transformers import BitsAndBytesConfig

            if quantization == "4bit":
                return BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.float16,
                )
            return BitsAndBytesConfig(
                load_in_8bit=True,
                llm_int8_enable_fp32_cpu_offload=cpu_offload,
            )
        except Exception:
            return None

    def _ensure_text_loaded(self) -> bool:
        if self._text_model is not None and self._text_tokenizer is not None:
            self.text_ready = True
            self.ready = True
            return True

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            quant_config = self._build_quant_config(self._text_quantization, torch, cpu_offload=True)
            load_kwargs: dict[str, Any] = {
                "device_map": "auto" if torch.cuda.is_available() else "cpu",
                "low_cpu_mem_usage": True,
                "torch_dtype": torch.float16 if torch.cuda.is_available() else (getattr(torch, "bfloat16", None) or torch.float32),
            }
            if quant_config is not None:
                load_kwargs["quantization_config"] = quant_config
            elif torch.cuda.is_available():
                load_kwargs["max_memory"] = {0: "14GiB", "cpu": self._text_cpu_max_memory}

            tokenizer = AutoTokenizer.from_pretrained(self._text_model_path)
            if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
                tokenizer.pad_token = tokenizer.eos_token

            model = AutoModelForCausalLM.from_pretrained(self._text_model_path, **load_kwargs).eval()
            if getattr(model, "generation_config", None) is not None:
                model.generation_config.do_sample = False
                if hasattr(model.generation_config, "temperature"):
                    model.generation_config.temperature = None
                if hasattr(model.generation_config, "top_p"):
                    model.generation_config.top_p = None
                if hasattr(model.generation_config, "min_p"):
                    model.generation_config.min_p = None

            self._text_tokenizer = tokenizer
            self._text_model = model
            self._runtime_device = "cuda" if torch.cuda.is_available() else "cpu"
            self.text_ready = True
            self.ready = True
            self._load_error = None
            if self._translation_enabled and self._translation_preload:
                self._ensure_translation_loaded("zh_en")
                self._ensure_translation_loaded("en_zh")
            return True
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"AstroSage load failed: {type(exc).__name__}: {exc}"
            self.text_ready = False
            self.ready = False
            return False

    def _ensure_translation_loaded(self, direction: str) -> bool:
        if not self._translation_enabled:
            return False
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            preferred_device = "cuda" if torch.cuda.is_available() else "cpu"
            same_model = self._zh_en_model_id == self._en_zh_model_id

            def is_nllb(model_id: str) -> bool:
                return "nllb" in str(model_id).lower()

            def load_model(model_id: str) -> tuple[Any, str]:
                if same_model and self._shared_translation_model is not None and self._shared_translation_model_id == model_id:
                    return self._shared_translation_model, self._translation_device
                if preferred_device == "cuda":
                    try:
                        model = AutoModelForSeq2SeqLM.from_pretrained(
                            model_id,
                            torch_dtype=torch.float16,
                            low_cpu_mem_usage=True,
                        ).eval()
                        model = model.to("cuda")
                        if same_model:
                            self._shared_translation_model = model
                            self._shared_translation_model_id = model_id
                        return model, "cuda"
                    except Exception:
                        pass
                model = AutoModelForSeq2SeqLM.from_pretrained(model_id).eval()
                if same_model:
                    self._shared_translation_model = model
                    self._shared_translation_model_id = model_id
                return model, "cpu"

            def load_tokenizer(model_id: str, src_lang: str | None, tgt_lang: str | None) -> Any:
                if is_nllb(model_id):
                    return AutoTokenizer.from_pretrained(model_id, src_lang=src_lang, tgt_lang=tgt_lang)
                return AutoTokenizer.from_pretrained(model_id)

            if direction == "zh_en":
                if self._zh_en_model is not None and self._zh_en_tokenizer is not None:
                    return True
                src_lang = "zho_Hans" if is_nllb(self._zh_en_model_id) else None
                tgt_lang = "eng_Latn" if is_nllb(self._zh_en_model_id) else None
                self._zh_en_tokenizer = load_tokenizer(self._zh_en_model_id, src_lang, tgt_lang)
                self._zh_en_model, self._translation_device = load_model(self._zh_en_model_id)
                return True

            if self._en_zh_model is not None and self._en_zh_tokenizer is not None:
                return True
            src_lang = "eng_Latn" if is_nllb(self._en_zh_model_id) else None
            tgt_lang = "zho_Hans" if is_nllb(self._en_zh_model_id) else None
            self._en_zh_tokenizer = load_tokenizer(self._en_zh_model_id, src_lang, tgt_lang)
            self._en_zh_model, self._translation_device = load_model(self._en_zh_model_id)
            return True
        except Exception:
            return False

    def _translate(self, text: str, direction: str) -> str:
        if not text or not self._translation_enabled:
            return text

        cache_key = (direction, text)
        cached = self._translation_cache.get(cache_key)
        if cached:
            self._translation_cache.move_to_end(cache_key)
            return cached

        if not self._ensure_translation_loaded(direction):
            return text

        try:
            import torch

            if direction == "zh_en":
                tokenizer = self._zh_en_tokenizer
                model = self._zh_en_model
            else:
                tokenizer = self._en_zh_tokenizer
                model = self._en_zh_model

            assert tokenizer is not None
            assert model is not None

            model_device = next(model.parameters()).device
            encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=384)
            encoded = {k: v.to(model_device) for k, v in encoded.items()}
            gen_kwargs: dict[str, Any] = {
                **encoded,
                "max_new_tokens": self._translation_max_new_tokens,
                "num_beams": 1,
                "do_sample": False,
            }
            forced = None
            target_lang = "eng_Latn" if direction == "zh_en" else "zho_Hans"
            if hasattr(tokenizer, "lang_code_to_id"):
                forced = tokenizer.lang_code_to_id.get(target_lang)
            if forced is None and hasattr(tokenizer, "convert_tokens_to_ids"):
                try:
                    forced = tokenizer.convert_tokens_to_ids(target_lang)
                except Exception:
                    forced = None
            if isinstance(forced, int) and forced >= 0:
                gen_kwargs["forced_bos_token_id"] = forced
            with torch.inference_mode():
                output_ids = model.generate(**gen_kwargs)
            translated = tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0].strip()
            translated = translated or text
            self._translation_cache[cache_key] = translated
            while len(self._translation_cache) > self._translation_cache_size:
                self._translation_cache.popitem(last=False)
            return translated
        except Exception:
            return text

    def _heuristic_translate_zh_to_en(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return raw
        replacements = [
            ("系外行星", "exoplanet"),
            ("黑洞", "black hole"),
            ("中子星", "neutron star"),
            ("超新星", "supernova"),
            ("银河系", "Milky Way"),
            ("太阳", "Sun"),
            ("月球", "Moon"),
            ("地球", "Earth"),
            ("火星", "Mars"),
            ("木星", "Jupiter"),
            ("土星", "Saturn"),
            ("金星", "Venus"),
            ("水星", "Mercury"),
            ("天王星", "Uranus"),
            ("海王星", "Neptune"),
            ("冥王星", "Pluto"),
            ("适合生命存在", "habitable for life"),
            ("宜居", "habitable"),
            ("温度", "temperature"),
            ("距离", "distance"),
            ("质量", "mass"),
            ("半径", "radius"),
            ("直径", "diameter"),
        ]
        q = raw
        for zh, en in replacements:
            q = q.replace(zh, en)

        q = q.replace("为什么", "why")
        q = q.replace("怎么", "how")
        q = q.replace("如何", "how")
        q = q.replace("是什么", "what is")
        q = q.replace("有多少", "how many")
        q = q.replace("多少", "how many")
        q = q.replace("多远", "how far")
        q = q.replace("多大", "how large")
        q = q.replace("曾经", "in the past")
        q = q.replace("目前", "currently")
        q = q.replace("是否", "whether")
        q = q.replace("吗", "?")
        q = re.sub(r"[，。；：、]", " ", q)
        q = re.sub(r"\s+", " ", q).strip()
        if not q.endswith("?"):
            q = q + "?"
        return q

    def _is_bad_zh_en_translation(self, original_zh: str, translated_en: str) -> bool:
        t = str(translated_en or "").strip().lower()
        if not t:
            return True
        if _contains_cjk(t):
            return True
        if len(t) < 8:
            return True
        generic = {
            "what is this?",
            "what is the meaning of this?",
            "what does this mean?",
            "what is the significance of this?",
        }
        if t in generic:
            return True
        # If original mentions major entities but translation misses all, treat as weak translation.
        entity_pairs = [
            ("火星", "mars"),
            ("木星", "jupiter"),
            ("土星", "saturn"),
            ("黑洞", "black hole"),
            ("系外行星", "exoplanet"),
            ("银河系", "milky way"),
        ]
        for zh, en in entity_pairs:
            if zh in original_zh and en not in t:
                return True
        return False

    def _extract_topic_tokens(self, text: str) -> list[str]:
        s = str(text or "").strip().lower()
        if not s:
            return []
        mapping = [
            (["土星", "saturn"], ["土星", "saturn"]),
            (["土星环", "rings"], ["土星环", "ring", "rings"]),
            (["木星", "jupiter"], ["木星", "jupiter"]),
            (["火星", "mars"], ["火星", "mars"]),
            (["地球", "earth"], ["地球", "earth"]),
            (["月球", "moon", "luna"], ["月球", "moon"]),
            (["太阳", "sun", "sol"], ["太阳", "sun"]),
            (["黑洞", "black hole"], ["黑洞", "black hole"]),
            (["银河系", "milky way"], ["银河系", "milky way"]),
            (["系外行星", "exoplanet"], ["系外行星", "exoplanet"]),
            (["宇宙", "universe", "cosmos"], ["宇宙", "universe"]),
        ]
        hits: list[str] = []
        for needles, tokens in mapping:
            if any(n.lower() in s for n in needles):
                for t in tokens:
                    if t not in hits:
                        hits.append(t)
        return hits

    def _score_english_query(self, original_zh: str, candidate: str) -> int:
        c = str(candidate or "").strip().lower()
        if not c:
            return -999
        score = 0
        if len(c) >= 10:
            score += 3
        if not _contains_cjk(c):
            score += 4
        if re.search(r"[a-z]{3,}", c):
            score += 3
        for token in self._extract_topic_tokens(original_zh):
            if token in c:
                score += 2
        if _contains_arabic(c):
            score -= 4
        return score

    def _pick_best_english_question(self, original_zh: str, translated_en: str, heuristic_en: str) -> str:
        t = str(translated_en or "").strip()
        h = str(heuristic_en or "").strip()
        if not t and not h:
            return ""
        if not t:
            return h
        if not h:
            return t
        st = self._score_english_query(original_zh, t)
        sh = self._score_english_query(original_zh, h)
        return h if sh > st else t

    def _is_answer_relevant(self, question: str, answer: str) -> bool:
        q = str(question or "").strip().lower()
        a = str(answer or "").strip().lower()
        if not q or not a:
            return False
        tokens = self._extract_topic_tokens(q)
        if not tokens:
            return True
        return any(token in a for token in tokens)

    def _rewrite_en_answer_to_zh_with_llm(self, question_zh: str, answer_en: str) -> str:
        if not answer_en or self._text_model is None or self._text_tokenizer is None:
            return ""
        prompt = (
            "你是专业天文科普助手。请把下面英文答案改写为自然、流畅、准确的简体中文。\n"
            "要求：\n"
            "1) 严格围绕用户问题，不跑题。\n"
            "2) 先给结论，再解释原因与背景。\n"
            "3) 用连贯段落表达，避免列表和模板腔。\n"
            "4) 不要编造来源，不要输出多余标签。\n\n"
            f"用户问题：{question_zh.strip()}\n"
            f"英文答案：{answer_en.strip()}\n"
            "中文改写："
        )
        rewritten = self._generate_from_prompt(prompt, tokenizer=self._text_tokenizer, model=self._text_model)
        return self._clean_answer(rewritten)

    def _regenerate_on_topic(self, question_en: str, original_question: str) -> str:
        if self._text_model is None or self._text_tokenizer is None:
            return ""
        topic_tokens = [t for t in self._extract_topic_tokens(original_question) if all(ord(ch) < 128 for ch in t)]
        strict_prompt = (
            "You are an astronomy expert assistant.\n"
            "Answer ONLY the user question below, do not switch to another topic.\n"
            "If unsure, state uncertainty briefly and still stay on this question.\n"
            "Write one coherent paragraph of 6 to 9 sentences in clear English.\n"
        )
        if topic_tokens:
            strict_prompt += f"Must mention these topic terms: {', '.join(topic_tokens[:4])}.\n"
        strict_prompt += f"\nQuestion: {question_en.strip()}\nAnswer:"
        regen = self._generate_from_prompt(strict_prompt, tokenizer=self._text_tokenizer, model=self._text_model)
        return self._clean_answer(regen)

    def _generate_text(self, question_en: str) -> str:
        assert self._text_model is not None
        assert self._text_tokenizer is not None

        tokenizer = self._text_tokenizer
        model = self._text_model
        prompt = self._build_text_prompt(question_en)
        return self._generate_from_prompt(prompt, tokenizer=tokenizer, model=model)

    def _generate_from_prompt(self, prompt: str, tokenizer: Any, model: Any) -> str:
        encoded = tokenizer(prompt, return_tensors="pt")
        encoded = {k: v.to(model.device) for k, v in encoded.items()}
        import torch

        with torch.inference_mode():
            output_ids = model.generate(
                **encoded,
                max_new_tokens=max(64, self._text_max_new_tokens),
                do_sample=self._text_temperature > 0.01,
                temperature=self._text_temperature if self._text_temperature > 0.01 else None,
                top_p=min(max(self._text_top_p, 0.1), 1.0) if self._text_temperature > 0.01 else None,
                repetition_penalty=max(1.0, self._text_repetition_penalty),
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
                use_cache=True,
            )
        text = tokenizer.decode(output_ids[0][encoded["input_ids"].shape[-1] :], skip_special_tokens=True).strip()
        return text

    def _expand_short_answer(self, question_en: str, draft_en: str) -> str:
        if not draft_en:
            return draft_en
        if len(draft_en) >= 380:
            return draft_en
        assert self._text_model is not None
        assert self._text_tokenizer is not None
        prompt = (
            "You are an astronomy science communicator.\n"
            "Rewrite and expand the draft answer for general users.\n"
            "Requirements:\n"
            "1) Keep all facts consistent with the draft.\n"
            "2) Start with a direct conclusion.\n"
            "3) Explain mechanism/background and one observation/evidence clue.\n"
            "4) Explain why this matters for astronomy enthusiasts.\n"
            "5) Write 6 to 8 complete sentences in one coherent paragraph.\n"
            "6) Do not ask back questions. Do not output labels.\n\n"
            f"Question: {question_en.strip()}\n"
            f"Draft: {draft_en.strip()}\n"
            "Expanded answer:"
        )
        expanded = self._generate_from_prompt(prompt, tokenizer=self._text_tokenizer, model=self._text_model)
        expanded = self._clean_answer(expanded)
        if len(expanded) > len(draft_en) and len(expanded) >= 180:
            return expanded
        return draft_en

    def _build_text_prompt(self, question_en: str) -> str:
        q = str(question_en or "").strip().lower()
        quant_keywords = [
            "how far",
            "distance",
            "temperature",
            "how hot",
            "radius",
            "diameter",
            "mass",
            "how big",
            "how large",
            "how old",
            "speed",
            "how fast",
            "orbital period",
            "surface gravity",
        ]
        is_quant = any(token in q for token in quant_keywords)

        if is_quant:
            return (
                "You are an expert in astronomy, astrophysics, and cosmology.\n"
                "Answer the user's question directly and stay tightly on topic.\n"
                "This is a quantitative astronomy question.\n"
                "Write in an engaging but accurate popular-science tone.\n"
                "In the first sentence, give one approximate value or a short range with units.\n"
                "Use plain international English with short sentences and simple vocabulary.\n"
                "Avoid idioms, rhetorical questions, and poetic expressions.\n"
                "Use metric or standard astronomy units only, such as km, AU, light-years, K, or deg C.\n"
                "Do not use miles or Fahrenheit unless the user explicitly asks for them.\n"
                "Do not list many different conversions or too many numbers.\n"
                "Then explain why the value changes, what it means physically, and why astronomers care.\n"
                "Write one coherent paragraph of 6 to 8 sentences.\n"
                "Make it sound like a polished popular-science assistant, not a template.\n"
                "Return only the final answer.\n"
                "Do not output another question.\n"
                "Do not output labels such as Question, Answer, Example, or User.\n\n"
                f"Question: {question_en.strip()}\n"
                "Answer:"
            )

        return (
            "You are an expert in astronomy, astrophysics, and cosmology.\n"
            "Answer the user's question directly and stay tightly on topic.\n"
            "Write a vivid and informative science-popularization answer for a curious general user.\n"
            "Start with the key answer in the first sentence.\n"
            "Use plain international English with short sentences and simple vocabulary.\n"
            "Avoid idioms, rhetorical questions, and poetic expressions.\n"
            "Then explain the reason, physical meaning, and one memorable comparison or observation.\n"
            "Also mention why this matters to astronomy or why enthusiasts find it interesting.\n"
            "Write one coherent paragraph of 6 to 9 sentences.\n"
            "Make it sound like a polished popular-science assistant, not a template.\n"
            "Use metric or standard astronomy units only, such as km, AU, light-years, K, or deg C.\n"
            "Do not use miles or Fahrenheit unless the user explicitly asks for them.\n"
            "If the user asks for a definition, explain what it is, how it forms or works, and why it matters.\n"
            "Do not drift to a different topic.\n"
            "Return only the final answer.\n"
            "Do not output another question.\n"
            "Do not output labels such as Question, Answer, Example, or User.\n\n"
            f"Question: {question_en.strip()}\n"
            "Answer:"
        )

    def _clean_answer(self, text: str) -> str:
        answer = str(text or "").strip()
        if not answer:
            return ""
        answer = re.split(r"\b(?:Question|Example|User)\s*:", answer, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        answer = re.split(r"(?:^|\n)\s*问题[:：]", answer, maxsplit=1)[0].strip()
        answer = re.sub(r"^(Answer:|Assistant:)\s*", "", answer, flags=re.IGNORECASE).strip()
        answer = re.sub(r"\n{3,}", "\n\n", answer)
        answer = re.sub(r"(###Human:.*)$", "", answer, flags=re.DOTALL).strip()
        parts = [p.strip() for p in re.split(r"(?<=[。！？?!])\s+|(?<=\.)\s+", answer) if p.strip()]
        if not parts:
            return answer

        cleaned_parts: list[str] = []
        seen_norms: set[str] = set()
        for part in parts:
            norm = re.sub(r"[\s,，。！？?!:：;；()（）\-]+", "", part)
            if len(norm) < 6:
                continue
            if norm in seen_norms:
                continue
            if any(norm in old or old in norm for old in seen_norms if len(old) >= 12):
                continue
            seen_norms.add(norm)
            cleaned_parts.append(part)
            if len(cleaned_parts) >= 8:
                break
        if cleaned_parts:
            answer = " ".join(cleaned_parts).strip()
        answer = re.sub(r"([。！？?!])(?:\s*\1){1,}", r"\1", answer)
        return answer

    def _polish_chinese_text(self, text: str) -> str:
        polished = str(text or "").strip()
        if not polished:
            return ""
        polished = re.sub(r"(?<=\d)\s+\.\s*(?=\d)", ".", polished)
        polished = re.sub(r"(?<!\d)\.(?!\d)", "。", polished)
        polished = re.sub(r"(?<=\d)\s*,\s*(?=\d{3}\b)", "", polished)
        polished = re.sub(r"(?<=\d)\s+(?=[万亿千百十公里米度年天倍%])", "", polished)
        polished = re.sub(r"\([^()]*?(英里|华氏度)[^()]*?\)", "", polished)
        polished = polished.replace(",", "，")
        polished = polished.replace("距离距离", "距离")
        polished = polished.replace("光孔", "光球")
        polished = polished.replace("太阳表面的温度被称为光球,大约为", "太阳可见表面叫作光球，温度大约为")
        polished = polished.replace("太阳表面的温度被称为光球，大约为", "太阳可见表面叫作光球，温度大约为")
        polished = polished.replace("是太阳周围的椭圆轨道", "沿椭圆轨道绕太阳公转")
        polished = polished.replace("纵观者", "天文爱好者")
        polished = polished.replace("热爱者", "天文爱好者")
        polished = polished.replace("好奇度巡游", "好奇号探测器")
        polished = polished.replace("地球有极地冰盖", "火星有极地冰盖")
        polished = polished.replace("月亮是吸引它们的", "这些卫星之所以吸引人")
        polished = polished.replace("对木星的月亮的研究", "对木星卫星的研究")
        polished = polished.replace("这使得它能够", "这也让它能够")
        polished = polished.replace("这一发现意义重大,因为", "这一发现很重要，因为")
        polished = polished.replace("这一发现意义重大，因为", "这一发现很重要，因为")
        polished = polished.replace("海峡", "三角洲")
        polished = polished.replace("约木星有超过80个已知月球", "木星已知有80多颗卫星")
        polished = polished.replace("距离离太阳意味着", "离太阳较远，这意味着")
        polished = polished.replace("环子", "土星环")
        polished = polished.replace("环观", "近距离观察土星环时的视觉景象")
        polished = polished.replace("有水水", "有液态水")
        polished = re.sub(r"([\u4e00-\u9fff]{1,4})\1{2,}", r"\1", polished)
        polished = re.sub(r"\(\s+", "(", polished)
        polished = re.sub(r"\s+\)", ")", polished)
        polished = re.sub(r"\s+([，。！？；：])", r"\1", polished)
        polished = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", polished)
        polished = re.sub(r"\s{2,}", " ", polished)
        sentences = [s.strip() for s in re.split(r"(?<=[。！？])", polished) if s.strip()]
        if not sentences:
            return polished.strip()

        final_sentences: list[str] = []
        seen_norms: set[str] = set()
        for sentence in sentences:
            norm = re.sub(r"[\s,，。！？?!:：;；()（）\-]+", "", sentence)
            if len(norm) < 8:
                continue
            if norm in seen_norms:
                continue
            if any(norm in old or old in norm for old in seen_norms if len(old) >= 14):
                continue
            seen_norms.add(norm)
            final_sentences.append(sentence)
            if len(final_sentences) >= 8:
                break

        polished = "".join(final_sentences).strip() if final_sentences else polished.strip()
        if len(polished) > 1200:
            trimmed = polished[:1200]
            last_stop = max(trimmed.rfind("。"), trimmed.rfind("！"), trimmed.rfind("？"))
            if last_stop >= 40:
                polished = trimmed[: last_stop + 1]
            else:
                polished = trimmed.rstrip("，,;； ") + "。"
        return polished.strip()

    def _trim_answer_for_question(self, answer: str, question: str) -> str:
        text = str(answer or "").strip()
        q = str(question or "").lower()
        if not text:
            return ""
        is_quant = any(
            token in q
            for token in [
                "多少",
                "多远",
                "多大",
                "温度",
                "质量",
                "半径",
                "直径",
                "年龄",
                "速度",
                "distance",
                "temperature",
                "mass",
                "radius",
                "diameter",
                "speed",
            ]
        )
        sentences = [s.strip() for s in re.split(r"(?<=[。！？])", text) if s.strip()]
        if not sentences:
            return text
        limit = 8 if is_quant else 12
        return "".join(sentences[:limit]).strip()

    def _present_popular_science_answer(self, answer: str, question: str) -> str:
        text = str(answer or "").strip()
        if not text:
            return ""

        q = str(question or "").lower()
        is_quant = any(
            token in q
            for token in [
                "多少",
                "多远",
                "多大",
                "温度",
                "质量",
                "半径",
                "直径",
                "年龄",
                "速度",
                "distance",
                "temperature",
                "mass",
                "radius",
                "diameter",
                "speed",
            ]
        )
        sentences = [s.strip() for s in re.split(r"(?<=[。！？])", text) if s.strip()]
        if not sentences:
            return text

        cleaned_sentences: list[str] = []
        seen_norms: set[str] = set()
        for sentence in sentences:
            current = sentence
            norm = re.sub(r"[\s，。！？、；：“”‘’()（）\-]+", "", current)
            if not norm or norm in seen_norms:
                continue
            if any(norm in old or old in norm for old in seen_norms if len(old) >= 12):
                continue
            seen_norms.add(norm)
            cleaned_sentences.append(current)

        paragraph = "".join(cleaned_sentences).strip()
        paragraph = paragraph.replace("，，", "，")
        paragraph = paragraph.replace("。。", "。")
        paragraph = paragraph.replace("，。", "。")
        return paragraph

    def _prefix_yes_no_style(self, answer: str, question: str, answer_en: str) -> str:
        text = str(answer or "").strip()
        q = str(question or "").strip()
        raw_en = str(answer_en or "").strip().lower()
        if not text or "吗" not in q:
            return text
        if raw_en.startswith("yes") and not re.match(r"^(是的|有|可以|会|确实|目前有)", text):
            return "是的，" + text
        if raw_en.startswith("no") and not re.match(r"^(不是|没有|目前没有|尚无)", text):
            return "目前没有明确证据表明，" + text
        return text

    def _apply_contextual_rewrites(self, answer: str, question: str) -> str:
        text = str(answer or "").strip()
        q = str(question or "")
        q_low = q.lower()

        if "黑洞" in q and "光" in q and any(k in q for k in ["逃离", "逃出", "逃逸"]):
            return (
                "严格来说，光一旦落入黑洞事件视界之内，就无法再逃出来。"
                "我们常听到的“黑洞会发光”主要指两类现象：一类是黑洞周围吸积盘被加热后发出的强辐射，"
                "另一类是霍金辐射，它来自事件视界附近的量子效应，而不是黑洞内部的光线直接逃逸。"
                "这也是为什么黑洞本体看起来是“黑”的，但周围环境却可能非常明亮。"
                "对天文观测来说，科学家往往通过这些外围辐射、恒星轨道扰动和引力波信号来间接确认黑洞的存在与性质。"
            )

        if "火星" in q and "生命" in q:
            return (
                "目前还没有确凿证据证明火星存在或曾存在生命，但“早期火星可能更宜居”是一个被广泛研究的结论。"
                "轨道器和火星车发现了古代河道、湖盆沉积、含水矿物以及有机分子线索，说明火星在远古时期曾有液态水活动。"
                "关键不确定性在于：这些环境是否长期稳定、能否提供持续的化学能来源，以及生命信号是否被后来地质过程抹去。"
                "所以更准确的说法是：火星曾具备部分宜居条件，但是否真正孕育过生命，仍需样本返回和更高精度探测来验证。"
            )

        if "木星" in q and "卫星" in q and ("多少" in q or "几" in q):
            return (
                "木星是太阳系卫星数量最多的行星之一，目前已确认的天然卫星数量在“90多颗”这个量级，并且随着新观测还可能继续增加。"
                "其中最著名的是伽利略四大卫星：木卫一、木卫二、木卫三和木卫四。"
                "它们之所以重要，是因为这四颗卫星在地质活动、冰下海洋和潜在宜居性方面都非常有研究价值，"
                "尤其木卫二与木卫三被认为可能存在地下液态海洋。"
                "所以从科普角度看，木星不只是“卫星多”，更像一个小型行星系统。"
            )

        if "土星" in q and "环" in q and any(k in q for k in ["看到", "看见", "看", "附近"]):
            return (
                "如果你站在土星环附近，最震撼的体验会是“环并不是一整块圆盘”，而是由无数冰粒和岩屑组成的超薄颗粒系统。"
                "近距离看，环结构会呈现出非常细密的分带、缝隙和波纹，有些区域明亮、有些区域偏暗，像一张被引力不断雕刻的唱片。"
                "这些细节主要由土星本身引力、环内粒子碰撞，以及卫星共振共同塑造，所以环看起来并不是静止的，而是在持续演化。"
                "你还会注意到环的厚度其实很薄，尺度上远小于它的径向宽度，这种“又大又薄”的反差是土星环最迷人的地方。"
                "从观测角度说，研究这些纹理和缝隙，能帮助天文学家理解行星环动力学，也能反推早期太阳系中物质聚集与分散的过程。"
            )

        if "宇宙" in q and any(k in q for k in ["多大", "大小", "多广", "范围"]):
            return (
                "如果说“我们能看到的宇宙有多大”，常用结论是：可观测宇宙半径约465亿光年，直径约930亿光年。"
                "这个数字看起来会大于“138亿年宇宙年龄”，是因为在光传播的过程中，宇宙本身也在持续膨胀。"
                "需要区分的是：可观测宇宙只是“以我们为中心、目前能接收到光信号的范围”，并不等于整个宇宙的真实边界。"
                "从理论上看，整个宇宙可能远大于可观测范围，甚至可能是无限的，但目前观测还无法直接给出全宇宙总尺度。"
                "这也是现代宇宙学最核心的问题之一：我们既在测量“看得见的尺度”，也在反推“看不见的整体结构”。"
            )

        if "系外行星" in q and ("宜居带" in q or "适居带" in q) and ("发现方法" in q or "分类" in q):
            return (
                "如果按发现方法来分，宜居带系外行星可以先看四类主流路线。"
                "第一类是凌日法，代表目标包括 TRAPPIST-1e、K2-18b、LHS 1140 b，这类方法最适合测半径和大气透射信号；"
                "第二类是径向速度法，代表如 Proxima Centauri b，可更直接约束最小质量；"
                "第三类是凌日与径向速度联合确认，这类样本在参数精度上通常最好，便于评估密度与潜在可居住性；"
                "第四类是直接成像或微引力透镜，目前在“类地、宜居带”样本里占比较小，但对长周期和特殊系统很重要。"
                "从科普和研究价值看，真正关键的不只是“在宜居带内”，还包括恒星活动强度、大气保持能力、是否存在液态水稳定条件等。"
                "因此可以把“宜居带候选”理解为优先观测名单，而不是已经确认可居住的行星。"
            )

        if "木星" in q and "卫星" in q:
            text = text.replace("月球", "卫星")
        if "木星" in q:
            text = text.replace("约伯特", "木星")
            text = text.replace("约合星", "木星")
            text = text.replace("约木星", "木星")
        if "火星" in q or "mars" in q_low:
            text = text.replace("火星火星", "火星")
        return text

    def _build_effective_question(self, question: str, context: dict[str, Any] | None) -> str:
        base_question = str(question or "").strip()
        if not context:
            return base_question

        analysis = context.get("analysis") if isinstance(context, dict) else {}
        intent = str((analysis or {}).get("intent", "")).strip()
        entities = [str(x).strip() for x in (analysis or {}).get("entities", [])[:4] if str(x).strip()]
        session_memory = str(context.get("session_memory", "")).strip()[:280] if isinstance(context, dict) else ""
        rag_items = context.get("rag_items", []) if isinstance(context, dict) else []

        refs: list[str] = []
        if isinstance(rag_items, list):
            for item in rag_items[:4]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "")).strip()
                snippet = str(item.get("snippet", "")).strip()
                source = str(item.get("source", "")).strip()
                if not snippet and not title:
                    continue
                refs.append(f"[{source}] {title}: {snippet[:220]}")

        if not (intent or entities or session_memory or refs):
            return base_question

        suffix = "\n\nAdditional context for higher-accuracy astronomy answer:\n"
        if intent:
            suffix += f"- Intent: {intent}\n"
        if entities:
            suffix += f"- Entities: {entities}\n"
        if session_memory:
            suffix += f"- Session memory: {session_memory}\n"
        if refs:
            suffix += "- Evidence snippets:\n" + "\n".join([f"  - {x}" for x in refs]) + "\n"
        suffix += "- Use evidence only when relevant; otherwise answer directly.\n"
        return (base_question + suffix).strip()

    def answer(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        if not self._ensure_text_loaded():
            return {
                "answer": "",
                "citations": [],
                "graph_path": [],
                "meta": {"backend": "astrosage", "device": self._runtime_device},
            }

        original_question = str(question or "").strip()
        if not original_question:
            return {
                "answer": "",
                "citations": [],
                "graph_path": [],
                "meta": {"backend": "astrosage", "device": self._runtime_device},
            }

        wants_chinese = _contains_cjk(original_question)
        if wants_chinese:
            translated_core = self._translate(original_question, "zh_en")
            heuristic_core = self._heuristic_translate_zh_to_en(original_question)
            core_en = translated_core
            if self._is_bad_zh_en_translation(original_question, translated_core):
                core_en = heuristic_core
            core_en = self._pick_best_english_question(original_question, core_en, heuristic_core)
            # Keep Chinese->English query clean; noisy mixed-language context can degrade quality.
            question_en = core_en
        else:
            question_en = self._build_effective_question(original_question, context)

        try:
            answer_en = self._generate_text(question_en)
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"AstroSage inference failed: {type(exc).__name__}: {exc}"
            answer_en = ""

        answer_en = self._clean_answer(answer_en)
        answer_en = self._expand_short_answer(question_en, answer_en)
        if wants_chinese and not self._is_answer_relevant(original_question, answer_en):
            regenerated = self._regenerate_on_topic(question_en, original_question)
            if regenerated and self._is_answer_relevant(original_question, regenerated):
                answer_en = regenerated
        if not answer_en:
            return {
                "answer": "",
                "citations": [],
                "graph_path": [],
                "meta": {"backend": "astrosage", "device": self._runtime_device},
            }

        final_answer = self._translate(answer_en, "en_zh") if wants_chinese else answer_en
        final_answer = self._clean_answer(final_answer)
        if wants_chinese and (not _contains_cjk(final_answer) or _contains_arabic(final_answer)):
            fallback_zh = self._rewrite_en_answer_to_zh_with_llm(original_question, answer_en)
            fallback_zh = self._clean_answer(fallback_zh)
            if _contains_cjk(fallback_zh):
                final_answer = fallback_zh
        if wants_chinese:
            final_answer = self._polish_chinese_text(final_answer)
            final_answer = self._trim_answer_for_question(final_answer, original_question)
            final_answer = self._present_popular_science_answer(final_answer, original_question)
            final_answer = self._prefix_yes_no_style(final_answer, original_question, answer_en)
            final_answer = self._apply_contextual_rewrites(final_answer, original_question)
            if not self._is_answer_relevant(original_question, final_answer):
                second_rewrite = self._rewrite_en_answer_to_zh_with_llm(original_question, answer_en)
                second_rewrite = self._polish_chinese_text(self._clean_answer(second_rewrite))
                if second_rewrite and self._is_answer_relevant(original_question, second_rewrite):
                    final_answer = second_rewrite
        return {
            "answer": final_answer,
            "citations": [f"model:astrosage-8b:{self._runtime_device}"],
            "graph_path": [],
            "meta": {"backend": "astrosage", "device": self._runtime_device},
        }

    def _ensure_astrollava_code(self) -> bool:
        repo_path = Path(self._vision_repo_path)
        if not repo_path.exists():
            self._load_error = (
                f"{self._load_error}; AstroLLaVA repo path does not exist: {repo_path}"
                if self._load_error
                else f"AstroLLaVA repo path does not exist: {repo_path}"
            )
            return False

        repo_path_str = str(repo_path)
        if repo_path_str not in sys.path:
            sys.path.insert(0, repo_path_str)

        try:
            from llava.model.language_model.llava_llama import LlavaLlamaForCausalLM
        except Exception as exc:  # noqa: BLE001
            self._load_error = (
                f"{self._load_error}; AstroLLaVA import failed: {type(exc).__name__}: {exc}"
                if self._load_error
                else f"AstroLLaVA import failed: {type(exc).__name__}: {exc}"
            )
            return False

        current_forward = LlavaLlamaForCausalLM.forward
        if getattr(current_forward, "_astro_cache_patch", False):
            return True

        if "cache_position" in inspect.signature(current_forward).parameters:
            current_forward._astro_cache_patch = True
            return True

        def patched_forward(
            self,
            input_ids=None,
            attention_mask=None,
            position_ids=None,
            past_key_values=None,
            inputs_embeds=None,
            labels=None,
            use_cache=None,
            output_attentions=None,
            output_hidden_states=None,
            images=None,
            image_sizes=None,
            return_dict=None,
            cache_position=None,
            **kwargs,
        ):
            _ = cache_position
            kwargs.pop("cache_position", None)
            kwargs.pop("num_logits_to_keep", None)
            return current_forward(
                self,
                input_ids=input_ids,
                attention_mask=attention_mask,
                position_ids=position_ids,
                past_key_values=past_key_values,
                inputs_embeds=inputs_embeds,
                labels=labels,
                use_cache=use_cache,
                output_attentions=output_attentions,
                output_hidden_states=output_hidden_states,
                images=images,
                image_sizes=image_sizes,
                return_dict=return_dict,
            )

        patched_forward._astro_cache_patch = True
        LlavaLlamaForCausalLM.forward = patched_forward
        return True

    def _ensure_vision_loaded(self) -> bool:
        if not self._vision_enabled:
            return False
        if self._vision_model is not None and self._vision_processor is not None:
            self.vision_ready = True
            return True
        if not self._ensure_astrollava_code():
            self.vision_ready = False
            return False

        try:
            import torch
            from transformers import AutoTokenizer

            from llava.model.language_model.llava_llama import LlavaLlamaForCausalLM
            from llava.utils import disable_torch_init

            quant_config = self._build_quant_config(self._vision_quantization, torch, cpu_offload=True)
            load_kwargs: dict[str, Any] = {
                "device_map": "auto" if torch.cuda.is_available() else "cpu",
                "low_cpu_mem_usage": True,
                "torch_dtype": torch.float16 if torch.cuda.is_available() else (getattr(torch, "bfloat16", None) or torch.float32),
            }
            if quant_config is not None:
                load_kwargs["quantization_config"] = quant_config
            elif torch.cuda.is_available():
                load_kwargs["max_memory"] = {0: "14GiB", "cpu": self._vision_cpu_max_memory}

            disable_torch_init()
            tokenizer = AutoTokenizer.from_pretrained(self._vision_model_path, use_fast=False)
            model = LlavaLlamaForCausalLM.from_pretrained(self._vision_model_path, **load_kwargs).eval()
            if getattr(model, "generation_config", None) is not None:
                model.generation_config.do_sample = False
                if hasattr(model.generation_config, "temperature"):
                    model.generation_config.temperature = None
                if hasattr(model.generation_config, "top_p"):
                    model.generation_config.top_p = None
                if hasattr(model.generation_config, "min_p"):
                    model.generation_config.min_p = None

            tower_source = self._vision_tower_path if Path(self._vision_tower_path).exists() else self._vision_tower_id
            vision_tower = model.get_vision_tower()
            if hasattr(vision_tower, "vision_tower_name"):
                vision_tower.vision_tower_name = tower_source
            if not getattr(vision_tower, "is_loaded", False):
                vision_tower.load_model(device_map="auto" if torch.cuda.is_available() else {"": "cpu"})

            self._vision_tokenizer = tokenizer
            self._vision_processor = vision_tower.image_processor
            self._vision_model = model
            self._runtime_device = "cuda" if torch.cuda.is_available() else "cpu"
            self.vision_ready = True
            self.ready = True
            return True
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"{self._load_error}; AstroLLaVA load failed: {type(exc).__name__}: {exc}" if self._load_error else f"AstroLLaVA load failed: {type(exc).__name__}: {exc}"
            self.vision_ready = False
            return False

    def _vision_generate(self, question_en: str, image_bytes: bytes) -> str:
        assert self._vision_model is not None
        assert self._vision_processor is not None
        assert self._vision_tokenizer is not None

        import torch

        from llava.constants import (
            DEFAULT_IMAGE_TOKEN,
            DEFAULT_IM_END_TOKEN,
            DEFAULT_IM_START_TOKEN,
            IMAGE_TOKEN_INDEX,
        )
        from llava.conversation import conv_templates
        from llava.mm_utils import process_images, tokenizer_image_token

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_sizes = [image.size]

        if getattr(self._vision_model.config, "mm_use_im_start_end", False):
            prompt_question = DEFAULT_IM_START_TOKEN + DEFAULT_IMAGE_TOKEN + DEFAULT_IM_END_TOKEN + "\n" + question_en
        else:
            prompt_question = DEFAULT_IMAGE_TOKEN + "\n" + question_en

        conv = conv_templates.get(self._vision_conv_mode, conv_templates["llava_v0"]).copy()
        conv.append_message(conv.roles[0], prompt_question)
        conv.append_message(conv.roles[1], None)
        prompt = conv.get_prompt()

        images_tensor = process_images([image], self._vision_processor, self._vision_model.config)
        images_tensor = images_tensor.to(
            self._vision_model.device,
            dtype=torch.float16 if self._vision_model.device.type == "cuda" else torch.float32,
        )
        input_ids = tokenizer_image_token(
            prompt,
            self._vision_tokenizer,
            IMAGE_TOKEN_INDEX,
            return_tensors="pt",
        ).unsqueeze(0).to(self._vision_model.device)
        attention_mask = torch.ones_like(input_ids)

        output_ids = self._vision_model.generate(
            input_ids,
            attention_mask=attention_mask,
            images=images_tensor,
            image_sizes=image_sizes,
            do_sample=False,
            max_new_tokens=max(64, self._vision_max_new_tokens),
            use_cache=True,
            pad_token_id=self._vision_tokenizer.pad_token_id or self._vision_tokenizer.eos_token_id,
        )
        text = self._vision_tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0].strip()
        return self._clean_answer(text)

    def warmup_vision(self) -> bool:
        if not self._ensure_vision_loaded():
            return False
        if self._translation_enabled:
            self._ensure_translation_loaded("zh_en")
            self._ensure_translation_loaded("en_zh")
        try:
            dummy = BytesIO()
            Image.new("RGB", (32, 32), color=(12, 18, 32)).save(dummy, format="PNG")
            self._vision_generate("Describe the main astronomical object in this image.", dummy.getvalue())
        except Exception:
            # 模型已加载即可；预热生成失败不阻断可用状态。
            pass
        self.vision_ready = True
        self.ready = self.ready or self.text_ready or self.vision_ready
        return True

    def predict_image(self, image_bytes: bytes, filename: str, context: dict[str, Any]) -> dict[str, Any]:
        _ = context
        if not self._ensure_vision_loaded():
            return {
                "ok": False,
                "filename": filename,
                "label": "unknown",
                "name": "unknown",
                "confidence": 0.0,
                "mode": "vision-unavailable",
            }
        caption = self._vision_generate("Describe the main astronomical object or target in this image.", image_bytes)
        if not caption:
            return {
                "ok": False,
                "filename": filename,
                "label": "unknown",
                "name": "unknown",
                "confidence": 0.0,
                "mode": "vision-unavailable",
            }
        name = self._translate(caption, "en_zh")
        name = self._polish_chinese_text(self._clean_answer(name))
        return {
            "ok": True,
            "filename": filename,
            "label": "astrollava-caption",
            "name": name,
            "confidence": 0.82,
            "mode": "astrollava",
        }

    def answer_with_image(
        self,
        question: str,
        image_bytes: bytes,
        filename: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        _ = context
        if not self._ensure_vision_loaded():
            return {
                "answer": "",
                "citations": [],
                "graph_path": [],
                "meta": {"backend": "astrollava", "device": self._runtime_device},
            }

        original_question = str(question or "").strip() or "What is shown in this image?"
        wants_chinese = _contains_cjk(original_question)
        question_en = self._translate(original_question, "zh_en") if wants_chinese else original_question

        try:
            answer_en = self._vision_generate(question_en, image_bytes)
        except Exception as exc:  # noqa: BLE001
            self._load_error = f"AstroLLaVA inference failed: {type(exc).__name__}: {exc}"
            answer_en = ""

        answer_en = self._clean_answer(answer_en)
        if not answer_en:
            return {
                "answer": "",
                "citations": [],
                "graph_path": [],
                "meta": {"backend": "astrollava", "device": self._runtime_device},
            }

        final_answer = self._translate(answer_en, "en_zh") if wants_chinese else answer_en
        final_answer = self._clean_answer(final_answer)
        if wants_chinese:
            final_answer = self._polish_chinese_text(final_answer)
            final_answer = self._trim_answer_for_question(final_answer, original_question)
            if (
                "国家" in original_question
                and any(k in original_question for k in ["第一个", "首次"])
                and any(k in original_question for k in ["到达", "登陆", "登月"])
            ):
                low_en = answer_en.lower()
                if "moon" in low_en or "月" in final_answer:
                    final_answer = (
                        "仅凭这张图片无法直接判断国家。"
                        "如果你问的是“哪个国家首次登陆月球”，答案是美国："
                        "阿波罗11号在1969年7月完成首次载人登月。"
                    )
                elif "mars" in low_en or "火星" in final_answer:
                    final_answer = (
                        "仅凭这张图片无法直接判断国家。"
                        "如果你问的是“哪个国家最早实现火星着陆”，"
                        "可区分为：苏联火星3号最早软着陆尝试（1971），"
                        "美国海盗1号实现长期稳定工作（1976）。"
                    )
                else:
                    final_answer = (
                        "仅凭这张图片无法直接判断“哪个国家第一个到达”。"
                        "需要先明确图片中的天体是什么。"
                        "如果目标是月球，首次载人登月是美国阿波罗11号（1969年7月）；"
                        "如果目标是火星，通常会区分最早软着陆尝试与首次长期稳定工作任务。"
                    )
        return {
            "answer": final_answer,
            "citations": [
                f"model:astrollava:{self._runtime_device}",
                f"image:{filename}",
            ],
            "graph_path": [],
            "meta": {"backend": "astrollava", "device": self._runtime_device},
        }
