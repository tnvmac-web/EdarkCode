"""Configuration for edarkcode."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATA_DIR = Path(os.environ.get("EDARKCODE_DATA_DIR", Path.home() / ".edarkcode"))


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096
    top_p: float = 1.0
    timeout: float = 120.0
    max_retries: int = 3
    retry_delay: float = 1.0


class MemoryConfig(BaseModel):
    enabled: bool = True
    path: Path = Field(default_factory=lambda: DEFAULT_DATA_DIR / "memory.jsonl")
    max_entries: int = 5000
    recall_limit: int = 5
    use_embeddings: bool = False


class SelfImprovementConfig(BaseModel):
    enabled: bool = True
    path: Path = Field(default_factory=lambda: DEFAULT_DATA_DIR / "lessons.jsonl")
    reflect_every: int = 1
    max_lessons: int = 1000


class AgentConfig(BaseModel):
    max_iterations: int = 40
    max_consecutive_errors: int = 3
    enable_planning: bool = True
    enable_reflection: bool = True
    auto_approve_tools: bool = False
    timeout_seconds: float = 900.0
    system_prompt: str | None = None


class UIConfig(BaseModel):
    theme: str = "dark"
    show_tool_calls: bool = True
    max_output_lines: int = 2000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EDARKCODE_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    self_improvement: SelfImprovementConfig = Field(default_factory=SelfImprovementConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    workspace: Path = Field(default_factory=Path.cwd)
    data_dir: Path = Field(default_factory=lambda: DEFAULT_DATA_DIR)
    log_level: str = "INFO"
    debug: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        cfg_path = path or (DEFAULT_DATA_DIR / "config.yaml")
        if cfg_path.exists():
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            return cls(**data)
        return cls()

    def save(self, path: Path | None = None) -> Path:
        cfg_path = path or (DEFAULT_DATA_DIR / "config.yaml")
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        return cfg_path
