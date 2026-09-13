"""settings 键默认值单源：路由展示与各消费方兜底共用（防两处漂移）。"""

DEFAULTS: dict = {
    "smtp_host": "",
    "smtp_port": 465,
    "smtp_user": "",
    "smtp_from": "",       # 空 → 发信地址回落 smtp_user
    "smtp_to": [],         # list[str]
    "threshold_warn": 0.8,
    "threshold_critical": 0.95,
    "sample_interval_seconds": 300,
    "timezone": "Asia/Shanghai",
}
