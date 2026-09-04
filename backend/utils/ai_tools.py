"""
AI Agent 工具 Schema(OpenAI Function Calling 格式)
供 utils/ai_agent.py (ReAct 流式) 使用的 25 个工具定义
执行实现在 utils/ai_tool_executor.py:TOOL_REGISTRY
"""
TOOLS = [
    # ---------- 待办 ----------
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": "查询用户的待办列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "done": {"type": "boolean", "description": "是否已完成,true=已完成,false=未完成"},
                    "limit": {"type": "integer", "description": "返回条数上限,默认 20,最大 100"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_todo",
            "description": "添加一个新的待办事项",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "待办内容"},
                    "due_date": {"type": "string", "description": "截止日期 YYYY-MM-DD,可选"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_todos_batch",
            "description": "在指定日期区间内批量创建同名待办(如'每天跑步'创建 7 天)",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "start_date": {"type": "string", "description": "起始日期 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"}
                },
                "required": ["text", "start_date", "end_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": "更新一个待办的内容、完成状态或截止日期",
            "parameters": {
                "type": "object",
                "properties": {
                    "todo_id": {"type": "integer"},
                    "text": {"type": "string"},
                    "done": {"type": "boolean"},
                    "due_date": {"type": "string"}
                },
                "required": ["todo_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_todo",
            "description": "删除一个待办",
            "parameters": {
                "type": "object",
                "properties": {"todo_id": {"type": "integer"}},
                "required": ["todo_id"]
            }
        }
    },
    # ---------- 目标 ----------
    {
        "type": "function",
        "function": {
            "name": "list_goals",
            "description": "查询用户的目标列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "done": {"type": "boolean", "description": "true=已完成,false=进行中"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_goal",
            "description": "添加一个新的长期目标",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "目标名称"},
                    "progress": {"type": "integer", "description": "初始进度 0-100,默认 0"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_goal",
            "description": "更新目标(改名、改进度、标完成)",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "progress": {"type": "integer"},
                    "done": {"type": "boolean"}
                },
                "required": ["goal_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_goal",
            "description": "删除一个目标",
            "parameters": {
                "type": "object",
                "properties": {"goal_id": {"type": "integer"}},
                "required": ["goal_id"]
            }
        }
    },
    # ---------- 收支 ----------
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": "查询用户的收支记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["income", "expense"]},
                    "year": {"type": "integer"},
                    "month": {"type": "integer"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_transaction",
            "description": "添加一笔收入或支出",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "type": {"type": "string", "enum": ["income", "expense"]},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "time": {"type": "string", "description": "YYYY-MM-DD HH:MM:SS"}
                },
                "required": ["amount", "type", "category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_transaction",
            "description": "更新一笔交易",
            "parameters": {
                "type": "object",
                "properties": {
                    "tx_id": {"type": "integer"},
                    "amount": {"type": "number"},
                    "type": {"type": "string", "enum": ["income", "expense"]},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "time": {"type": "string"}
                },
                "required": ["tx_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_transaction",
            "description": "删除一笔交易",
            "parameters": {
                "type": "object",
                "properties": {"tx_id": {"type": "integer"}},
                "required": ["tx_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_summary",
            "description": "获取某个月的收支汇总(收入/支出/净额)",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string", "description": "月份 YYYY-MM"}
                },
                "required": ["month"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_stats",
            "description": "获取某日的收支统计",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"}
                },
                "required": ["date"]
            }
        }
    },
    # ---------- 饮食 ----------
    {
        "type": "function",
        "function": {
            "name": "list_meals",
            "description": "查询用户的饮食记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD,可省"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_meal",
            "description": "记录一餐(包含食物项,自动算总卡路里)",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner"]},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "portion": {"type": "string"},
                                "calories": {"type": "number"}
                            },
                            "required": ["name", "calories"]
                        }
                    },
                    "date": {"type": "string", "description": "YYYY-MM-DD,默认今天"}
                },
                "required": ["meal_type", "items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_meal",
            "description": "更新一餐(整组重写)",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_id": {"type": "integer"},
                    "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner"]},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "portion": {"type": "string"},
                                "calories": {"type": "number"}
                            },
                            "required": ["name", "calories"]
                        }
                    },
                    "date": {"type": "string"}
                },
                "required": ["meal_id", "meal_type", "items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_meal",
            "description": "删除一餐(连带食物项)",
            "parameters": {
                "type": "object",
                "properties": {"meal_id": {"type": "integer"}},
                "required": ["meal_id"]
            }
        }
    },
    # ---------- 提醒 ----------
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "查询用户的提醒列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean", "description": "true=启用,false=停用"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_reminder",
            "description": "添加一个定时提醒",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["finance", "diet", "todo", "goal", "other"]},
                    "time": {"type": "string", "description": "HH:MM:SS"},
                    "enabled": {"type": "boolean", "description": "默认 true"}
                },
                "required": ["type", "time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_reminder",
            "description": "更新一个提醒",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer"},
                    "type": {"type": "string", "enum": ["finance", "diet", "todo", "goal", "other"]},
                    "time": {"type": "string"},
                    "enabled": {"type": "boolean"}
                },
                "required": ["reminder_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": "删除一个提醒",
            "parameters": {
                "type": "object",
                "properties": {"reminder_id": {"type": "integer"}},
                "required": ["reminder_id"]
            }
        }
    },
    # ---------- 用户设置 ----------
    {
        "type": "function",
        "function": {
            "name": "get_user_settings",
            "description": "查询用户偏好设置(每日卡路里目标等)",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_settings",
            "description": "更新用户偏好设置(目前仅支持每日卡路里目标)",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_calories": {"type": "integer", "description": "500-10000"}
                }
            }
        }
    }
]
