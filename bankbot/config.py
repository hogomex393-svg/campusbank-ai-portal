"""Read task-local configuration without logging credentials."""
from dataclasses import dataclass, field
from pathlib import Path
import os
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def read_env(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    return values


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    timeout_seconds: float = 45
    max_tool_rounds: int = 3
    history_turns: int = 6
    max_tokens: int = 1600
    provider: str = 'deepseek'
    open_staff_testing: bool = False
    retrieval_threshold: float = 0.18
    data_dir: Path = ROOT / "data"
    database_path: Path | None = None
    cloud_mode: bool = False
    public_url: str = ""
    bootstrap_code: str = field(default="", repr=False)
    test_access_code: str = field(default="", repr=False)

    @classmethod
    def load(cls):
        values = read_env(ROOT / ".env")
        def val(name, default):
            return os.environ.get(name, values.get(name, default))
        deployment=val('BANKBOT_DEPLOYMENT','local')
        if deployment not in ('local','cloud'):
            raise ValueError('BANKBOT_DEPLOYMENT must be local or cloud.')
        database=val('BANKBOT_DB_PATH','')
        if not database and os.environ.get('RAILWAY_VOLUME_MOUNT_PATH'):
            database=str(Path(os.environ['RAILWAY_VOLUME_MOUNT_PATH'])/'portal.sqlite3')
        public_url=val('BANKBOT_PUBLIC_URL','').rstrip('/')
        if not public_url and os.environ.get('RAILWAY_PUBLIC_DOMAIN'):
            public_url='https://'+os.environ['RAILWAY_PUBLIC_DOMAIN']
        cloud=deployment=='cloud'
        bootstrap=val('BANKBOT_BOOTSTRAP_CODE','')
        access=val('BANKBOT_TEST_ACCESS_CODE','')
        provider=val('LLM_PROVIDER','deepseek').lower()
        if provider not in ('deepseek','qwen','openai_compatible'):raise ValueError('Unsupported LLM_PROVIDER.')
        fallback_key=val('DEEPSEEK_API_KEY','') if provider=='deepseek' else val('DASHSCOPE_API_KEY','') if provider=='qwen' else ''
        fallback_base=val('DEEPSEEK_BASE_URL','https://api.deepseek.com') if provider=='deepseek' else val('DASHSCOPE_BASE_URL','https://dashscope.aliyuncs.com/compatible-mode/v1') if provider=='qwen' else ''
        fallback_model=val('DEEPSEEK_MODEL','deepseek-v4-pro') if provider=='deepseek' else 'qwen3.7-plus' if provider=='qwen' else ''
        if cloud:
            if not database or not Path(database).is_absolute():
                raise ValueError('Cloud mode requires an absolute BANKBOT_DB_PATH on a persistent volume.')
            if len(bootstrap)<24 or len(access)<12:
                raise ValueError('Cloud mode requires BANKBOT_BOOTSTRAP_CODE (24+ characters) and BANKBOT_TEST_ACCESS_CODE (12+ characters).')
            if public_url:
                parsed=urlparse(public_url)
                if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                    raise ValueError('BANKBOT_PUBLIC_URL must be a bare HTTPS origin, without a path or credentials.')
        return cls(
            api_key=val('LLM_API_KEY',fallback_key),
            base_url=val('LLM_BASE_URL',fallback_base).rstrip("/"),
            model=val('LLM_MODEL',fallback_model),
            provider=provider,max_tokens=max(300,min(int(val('LLM_MAX_TOKENS','1600')),6000)),
            open_staff_testing=val('BANKBOT_OPEN_STAFF_TESTING','false').lower() in ('true','1','yes'),
            timeout_seconds=max(1, min(float(val("BANKBOT_TIMEOUT_SECONDS", "45")), 120)),
            max_tool_rounds=max(1, min(int(val("BANKBOT_MAX_TOOL_ROUNDS", "3")), 5)),
            history_turns=max(1, min(int(val("BANKBOT_HISTORY_TURNS", "6")), 20)),
            database_path=Path(database) if database else None,
            cloud_mode=cloud,public_url=public_url,bootstrap_code=bootstrap,test_access_code=access,
        )
