# MAPE-K Dashboard Configuration Management System

## Overview
Centralized configuration management for all MAPE-K agents, allowing real-time updates without restarting services.

---

## 1. Configuration Storage Architecture

```
config/
├── agents/
│   ├── monitor.json
│   ├── analyzer.json
│   ├── planner.json
│   └── executor.json
├── llm/
│   ├── models.json
│   └── prompts/
│       ├── analyzer_prompts.json
│       └── planner_prompts.json
├── system/
│   ├── safety.json
│   ├── alerts.json
│   └── knowledge_base.json
└── workflows/
    ├── retry_policy.json
    └── priority_rules.json
```

---

## 2. Monitor Agent Configuration

**File**: `config/agents/monitor.json`

```json
{
  "agent_name": "Monitor",
  "enabled": true,
  "settings": {
    "polling_interval_seconds": 30,
    "max_concurrent_workflows": 50,
    "workflow_states_to_monitor": ["Failed", "Held", "Running"],
    "auto_analyze_failures": true,
    "metadata_collection": {
      "enabled": true,
      "extract_transformations": true,
      "extract_replicas": true,
      "extract_job_out_files": true
    },
    "failure_detection": {
      "check_pegasus_analyzer": true,
      "check_condor_logs": true,
      "extract_stderr": true
    },
    "paths": {
      "pegasus_submit_dir": "/home/user/workflows",
      "pegasus_analyzer_path": "/usr/bin/pegasus-analyzer"
    },
    "retry_policy": {
      "max_retries": 3,
      "retry_delay_seconds": 60,
      "exponential_backoff": true
    }
  },
  "notifications": {
    "send_on_failure_detected": true,
    "send_on_workflow_completed": false,
    "notification_channels": ["dashboard", "webhook"]
  },
  "advanced": {
    "ignore_workflow_patterns": ["test_*", "debug_*"],
    "priority_workflows": ["production_*"],
    "historical_workflow_tracking": true,
    "max_workflow_history": 100
  }
}
```

---

## 3. Analyzer Agent Configuration

**File**: `config/agents/analyzer.json`

```json
{
  "agent_name": "Analyzer",
  "enabled": true,
  "settings": {
    "llm_provider": "ollama",
    "llm_model": "llama3.3:70b",
    "llm_endpoint": "http://localhost:11434",
    "llm_timeout_seconds": 120,
    "max_tokens": 4096,
    "temperature": 0.1,
    "use_knowledge_base": true,
    "analysis_types": {
      "failed_workflows": {
        "enabled": true,
        "priority": "high",
        "prompt_template": "analyzer_failed_workflow"
      },
      "held_workflows": {
        "enabled": true,
        "priority": "medium",
        "prompt_template": "analyzer_held_workflow"
      }
    },
    "error_prioritization": {
      "prioritize_stderr_over_logs": true,
      "ignore_cascade_errors": true,
      "root_cause_detection": true
    },
    "file_request_policy": {
      "max_files_to_request": 5,
      "auto_request_transformation_files": true,
      "forbidden_files": ["/etc/passwd", "*.key", "*.pem"]
    }
  },
  "performance": {
    "max_concurrent_analyses": 3,
    "queue_processing_mode": "fifo",
    "cache_analysis_results": true,
    "cache_ttl_hours": 24
  },
  "notifications": {
    "send_on_analysis_complete": true,
    "send_on_analysis_failed": true,
    "notification_severity_threshold": "warning"
  }
}
```

---

## 4. Planner Agent Configuration

**File**: `config/agents/planner.json`

```json
{
  "agent_name": "Planner",
  "enabled": true,
  "settings": {
    "llm_provider": "ollama",
    "llm_model": "llama3.3:70b",
    "llm_endpoint": "http://localhost:11434",
    "llm_timeout_seconds": 180,
    "max_tokens": 8192,
    "temperature": 0.2,
    "planning_mode": "catalog_aware",
    "multi_stage_planning": true,
    "plan_validation": {
      "validate_before_sending": true,
      "check_file_existence": true,
      "syntax_check_python": true,
      "risk_assessment": true
    },
    "plan_types": {
      "code_fix": {
        "enabled": true,
        "require_approval": false,
        "max_file_changes": 10
      },
      "catalog_update": {
        "enabled": true,
        "require_approval": true,
        "allowed_catalog_operations": ["add_replica", "update_pfn"]
      },
      "resource_adjustment": {
        "enabled": true,
        "require_approval": false,
        "max_memory_gb": 64,
        "max_cpu_cores": 32
      },
      "dependency_fix": {
        "enabled": true,
        "require_approval": true,
        "allow_package_install": false
      }
    }
  },
  "safety": {
    "require_manual_approval": false,
    "dry_run_mode": false,
    "blacklisted_operations": ["rm -rf", "DROP TABLE", "sudo"],
    "whitelisted_paths": ["/home/user/workflows", "/tmp"],
    "max_plan_size_kb": 100
  },
  "notifications": {
    "send_on_plan_generated": true,
    "send_on_plan_rejected": true,
    "send_high_risk_plans": true
  }
}
```

---

## 5. Executor Agent Configuration

**File**: `config/agents/executor.json`

```json
{
  "agent_name": "Executor",
  "enabled": false,
  "settings": {
    "execution_mode": "safe",
    "dry_run_first": true,
    "create_backup_before_execution": true,
    "rollback_on_failure": true,
    "execution_timeout_seconds": 600,
    "max_concurrent_executions": 1,
    "plan_execution_order": {
      "validate_plan": 1,
      "create_backup": 2,
      "execute_actions": 3,
      "verify_success": 4,
      "cleanup_or_rollback": 5
    }
  },
  "safety": {
    "require_manual_approval": true,
    "approval_timeout_minutes": 30,
    "auto_reject_high_risk": true,
    "safety_checks": {
      "validate_file_paths": true,
      "check_disk_space": true,
      "verify_permissions": true,
      "scan_for_dangerous_commands": true
    },
    "allowed_operations": [
      "edit_file",
      "add_catalog_entry",
      "update_workflow_config",
      "install_package"
    ],
    "forbidden_operations": [
      "delete_file",
      "drop_database",
      "modify_system_files",
      "execute_shell_script"
    ]
  },
  "backup": {
    "backup_location": "/home/user/backups",
    "max_backups_per_workflow": 10,
    "backup_retention_days": 7,
    "compress_backups": true
  },
  "resubmission": {
    "auto_resubmit_workflow": true,
    "wait_before_resubmit_seconds": 30,
    "max_resubmit_attempts": 3,
    "pegasus_submit_command": "pegasus-run"
  },
  "notifications": {
    "send_on_execution_start": true,
    "send_on_execution_complete": true,
    "send_on_execution_failed": true,
    "send_on_rollback": true
  }
}
```

---

## 6. LLM Prompts Configuration

**File**: `config/llm/prompts/analyzer_prompts.json`

```json
{
  "prompts": {
    "analyzer_failed_workflow": {
      "name": "Analyzer - Failed Workflow",
      "version": "2.0",
      "last_updated": "2025-01-30",
      "system_prompt": "You are an expert workflow analyzer...",
      "user_prompt_template": "Analyze this failed workflow:\n\n{workflow_data}\n\nStderr:\n{stderr}\n\n...",
      "output_format": "json",
      "examples": [
        {
          "input": "...",
          "expected_output": "..."
        }
      ],
      "guidelines": [
        "Prioritize stderr over pegasus-analyzer logs",
        "Identify root cause, not cascade symptoms",
        "Only request files if absolutely necessary"
      ]
    },
    "analyzer_held_workflow": {
      "name": "Analyzer - Held Workflow",
      "version": "1.5",
      "last_updated": "2025-01-30",
      "system_prompt": "...",
      "user_prompt_template": "...",
      "output_format": "json"
    }
  }
}
```

---

## 7. Safety & Security Configuration

**File**: `config/system/safety.json`

```json
{
  "global_safety": {
    "enabled": true,
    "safety_level": "strict",
    "require_audit_log": true,
    "max_actions_per_workflow": 10
  },
  "file_operations": {
    "allowed_extensions": [".py", ".sh", ".yml", ".yaml", ".json"],
    "forbidden_extensions": [".key", ".pem", ".p12", ".pfx"],
    "allowed_paths": [
      "/home/user/workflows",
      "/tmp/pegasus",
      "/scratch/workflows"
    ],
    "forbidden_paths": [
      "/etc",
      "/usr",
      "/bin",
      "/sbin",
      "/root",
      "~/.ssh"
    ],
    "max_file_size_mb": 10
  },
  "command_execution": {
    "allowed_commands": [
      "pegasus-run",
      "pegasus-analyzer",
      "pegasus-status",
      "conda",
      "pip"
    ],
    "forbidden_commands": [
      "rm -rf",
      "sudo",
      "chmod 777",
      "chown",
      "dd",
      "mkfs",
      "DROP",
      "DELETE",
      "TRUNCATE"
    ],
    "command_timeout_seconds": 300
  },
  "catalog_operations": {
    "allowed_operations": ["add", "update", "read"],
    "forbidden_operations": ["delete", "truncate"],
    "require_approval_for": ["update", "add"],
    "validate_pfns": true
  },
  "rollback": {
    "enabled": true,
    "auto_rollback_on_error": true,
    "keep_rollback_backup_days": 7
  }
}
```

---

## 8. Alert & Notification Configuration

**File**: `config/system/alerts.json`

```json
{
  "alert_rules": [
    {
      "name": "Multiple Failures",
      "enabled": true,
      "condition": {
        "type": "count",
        "metric": "workflow_failures",
        "threshold": 3,
        "window_minutes": 10
      },
      "severity": "critical",
      "channels": ["email", "slack", "dashboard"],
      "message_template": "⚠️ {count} workflows failed in the last {window} minutes",
      "cooldown_minutes": 30
    },
    {
      "name": "Analyzer Timeout",
      "enabled": true,
      "condition": {
        "type": "timeout",
        "agent": "analyzer",
        "threshold_seconds": 180
      },
      "severity": "warning",
      "channels": ["dashboard", "webhook"],
      "message_template": "Analyzer is taking longer than expected"
    },
    {
      "name": "High Risk Plan Generated",
      "enabled": true,
      "condition": {
        "type": "event",
        "event": "plan_generated",
        "filter": "risk_level == 'high'"
      },
      "severity": "warning",
      "channels": ["email", "dashboard"],
      "message_template": "High-risk plan generated for {workflow_id}. Manual approval required.",
      "require_acknowledgment": true
    },
    {
      "name": "Agent Offline",
      "enabled": true,
      "condition": {
        "type": "health_check",
        "agent": "any",
        "status": "offline",
        "duration_minutes": 5
      },
      "severity": "critical",
      "channels": ["email", "slack", "sms"],
      "message_template": "🔴 {agent_name} has been offline for {duration}"
    }
  ],
  "notification_channels": {
    "email": {
      "enabled": true,
      "smtp_server": "smtp.gmail.com",
      "smtp_port": 587,
      "from_address": "mapek@example.com",
      "to_addresses": ["admin@example.com"],
      "use_tls": true
    },
    "slack": {
      "enabled": true,
      "webhook_url": "https://hooks.slack.com/services/...",
      "channel": "#mapek-alerts",
      "username": "MAPE-K Bot",
      "icon_emoji": ":robot_face:"
    },
    "webhook": {
      "enabled": true,
      "url": "https://api.example.com/webhooks/mapek",
      "method": "POST",
      "headers": {
        "Authorization": "Bearer ...",
        "Content-Type": "application/json"
      }
    },
    "dashboard": {
      "enabled": true,
      "show_toast": true,
      "play_sound": true,
      "desktop_notification": true
    }
  }
}
```

---

## 9. Knowledge Base Configuration

**File**: `config/system/knowledge_base.json`

```json
{
  "error_patterns": [
    {
      "id": "syntax_error_python",
      "pattern": "SyntaxError.*line (\\d+)",
      "category": "code_error",
      "severity": "high",
      "common_causes": [
        "Missing colon after function definition",
        "Incorrect indentation",
        "Missing closing bracket/parenthesis"
      ],
      "suggested_fix": "Check syntax at reported line number and surrounding lines",
      "auto_fixable": false,
      "requires_file": true
    },
    {
      "id": "import_error",
      "pattern": "ImportError: No module named '(.*)'",
      "category": "dependency_error",
      "severity": "medium",
      "common_causes": [
        "Missing package in environment",
        "Wrong conda environment activated"
      ],
      "suggested_fix": "Install missing package: pip install {package_name}",
      "auto_fixable": true,
      "requires_file": false
    },
    {
      "id": "out_of_memory",
      "pattern": "MemoryError|Killed.*memory",
      "category": "resource_error",
      "severity": "high",
      "common_causes": [
        "Insufficient memory allocated",
        "Memory leak in code",
        "Processing too much data at once"
      ],
      "suggested_fix": "Increase memory: request_memory = {current_memory * 2}GB",
      "auto_fixable": true,
      "requires_file": false
    }
  ],
  "successful_repairs": [
    {
      "workflow_id": "example_wf_123",
      "error_type": "ImportError",
      "fix_applied": "Added missing package to conda environment",
      "success": true,
      "timestamp": "2025-01-15T10:30:00Z",
      "notes": "Required numpy version >=1.20"
    }
  ],
  "settings": {
    "enable_learning": true,
    "auto_add_successful_fixes": true,
    "pattern_matching_threshold": 0.8,
    "max_patterns": 1000
  }
}
```

---

## 10. Dashboard API Endpoints for Configuration

```python
# GET endpoints
GET /api/config/agents/{agent_name}          # Get agent config
GET /api/config/llm/models                    # Get available LLM models
GET /api/config/llm/prompts/{prompt_name}     # Get prompt template
GET /api/config/safety                        # Get safety settings
GET /api/config/alerts                        # Get alert rules
GET /api/config/knowledge_base                # Get error patterns

# PUT endpoints
PUT /api/config/agents/{agent_name}           # Update agent config
PUT /api/config/llm/prompts/{prompt_name}     # Update prompt
PUT /api/config/safety                        # Update safety settings
PUT /api/config/alerts/{rule_name}            # Update alert rule

# POST endpoints
POST /api/config/alerts                       # Create new alert rule
POST /api/config/knowledge_base/patterns      # Add error pattern
POST /api/config/reload                       # Reload all configs

# DELETE endpoints
DELETE /api/config/alerts/{rule_name}         # Delete alert rule
```

---

## 11. Configuration Change Flow

```
User edits config in Dashboard UI
          ↓
Dashboard validates config (JSON schema)
          ↓
Dashboard sends PUT request to Config API
          ↓
Config API saves to file + database
          ↓
Config API broadcasts "config_changed" event via WebSocket
          ↓
Affected agent(s) receive event and reload config
          ↓
Agent confirms config reloaded successfully
          ↓
Dashboard shows success notification
```

---

## 12. UI Components Needed

### Configuration Management Page

```
┌─────────────────────────────────────────────┐
│  ⚙️ MAPE-K Configuration                    │
├─────────────────────────────────────────────┤
│                                             │
│  📡 Monitor Agent          [Enabled ✓]     │
│  ├── Polling Interval: [30] seconds        │
│  ├── Max Workflows: [50]                   │
│  └── Auto-Analyze: [✓] Yes                 │
│                                             │
│  🔬 Analyzer Agent         [Enabled ✓]     │
│  ├── LLM Model: [llama3.3:70b] ▼          │
│  ├── Temperature: [0.1] ━━━━○────          │
│  └── Max Tokens: [4096]                    │
│                                             │
│  📋 Planner Agent          [Enabled ✓]     │
│  ├── Planning Mode: [catalog_aware] ▼      │
│  ├── Require Approval: [✗] No             │
│  └── Max File Changes: [10]                │
│                                             │
│  ⚙️ Executor Agent         [Disabled ✗]    │
│  ├── Execution Mode: [safe] ▼              │
│  ├── Dry Run First: [✓] Yes               │
│  └── Manual Approval: [✓] Required        │
│                                             │
│  [Save Changes]  [Reset]  [Export Config]  │
└─────────────────────────────────────────────┘
```

---

This configuration system allows you to:

1. **Control all agents** from dashboard without restarting services
2. **Edit LLM prompts** in real-time to improve accuracy
3. **Configure safety rules** to prevent dangerous operations
4. **Set up custom alerts** for your specific needs
5. **Build knowledge base** of known errors and fixes
6. **Enable/disable features** dynamically
7. **Adjust performance** (concurrency, timeouts, caching)

Would you like me to start implementing this configuration management system?
