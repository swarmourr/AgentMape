#!/usr/bin/env python3
"""
Workflow-Specific Interaction Logger for Analyzer
Creates a separate database for each workflow ID
Logs EVERYTHING: LLM interactions, prints, outputs, all JSON data
"""

import uuid
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from tinydb import TinyDB, Query
from io import StringIO
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class WorkflowInteractionLogger:
    """
    Creates a separate interaction log database for each workflow
    Captures all output, prints, and LLM interactions
    """

    def __init__(self, workflow_id: str, base_dir: str = "workflow_logs"):
        """
        Initialize logger for a specific workflow

        Args:
            workflow_id: Unique workflow identifier
            base_dir: Base directory for storing workflow logs
        """
        self.workflow_id = workflow_id
        self.base_dir = base_dir

        # Print debug information
        print(f"\n{'='*80}")
        print(f"🔧 WORKFLOW INTERACTION LOGGER INITIALIZATION")
        print(f"{'='*80}")
        print(f"Workflow ID: {workflow_id}")
        print(f"Base directory: {base_dir}")

        # Create directory structure: workflow_logs/{workflow_id}/
        self.workflow_dir = os.path.join(base_dir, workflow_id)

        print(f"\n📁 Creating directory structure...")
        print(f"   Target directory: {self.workflow_dir}")

        # Check if directory already exists
        if os.path.exists(self.workflow_dir):
            print(f"   ✓ Directory already exists")
        else:
            print(f"   → Creating new directory...")
            os.makedirs(self.workflow_dir, exist_ok=True)

            # Verify creation
            if os.path.exists(self.workflow_dir):
                print(f"   ✓ Directory created successfully!")
            else:
                print(f"   ✗ ERROR: Failed to create directory!")

        # Get absolute path
        abs_path = os.path.abspath(self.workflow_dir)
        print(f"   Absolute path: {abs_path}")

        # Database file: workflow_logs/{workflow_id}/interactions.json
        self.db_path = os.path.join(self.workflow_dir, "interactions.json")

        print(f"\n💾 Creating database...")
        print(f"   Database path: {self.db_path}")
        print(f"   Absolute path: {os.path.abspath(self.db_path)}")

        self.db = TinyDB(self.db_path)

        # Verify database file was created
        if os.path.exists(self.db_path):
            file_size = os.path.getsize(self.db_path)
            print(f"   ✓ Database file created successfully!")
            print(f"   File size: {file_size} bytes")
        else:
            print(f"   ✗ ERROR: Database file not found!")

        # Tables
        print(f"\n📊 Creating tables...")
        self.llm_interactions = self.db.table('llm_interactions')
        print(f"   ✓ llm_interactions table")
        self.outputs = self.db.table('outputs')
        print(f"   ✓ outputs table")
        self.events = self.db.table('events')
        print(f"   ✓ events table")

        # Session tracking
        self.session_id = str(uuid.uuid4())
        self.session_start = datetime.now().isoformat()

        # Output capture
        self.captured_outputs = []

        print(f"\n✨ Session Information:")
        print(f"   Session ID: {self.session_id}")
        print(f"   Start time: {self.session_start}")

        logger.info(f"WorkflowInteractionLogger initialized for workflow: {workflow_id}")
        logger.info(f"Database: {self.db_path}")

        # Log session start
        print(f"\n📝 Logging session start event...")
        self.log_event("session_start", {
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "start_time": self.session_start
        })

        # Verify event was logged
        event_count = len(self.events.all())
        print(f"   ✓ Session start event logged (total events: {event_count})")

        print(f"\n{'='*80}")
        print(f"✅ WORKFLOW LOGGER READY!")
        print(f"{'='*80}\n")

    def log_llm_request(
        self,
        prompt: str,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Log LLM request

        Args:
            prompt: The prompt sent to LLM
            metadata: Additional metadata

        Returns:
            interaction_id
        """
        interaction_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        record = {
            "interaction_id": interaction_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "timestamp": timestamp,
            "type": "llm_request",
            "agent": "Analyzer",
            "prompt": prompt,
            "prompt_length": len(prompt),
            "metadata": metadata or {},
            "response": None,
            "response_length": None,
            "latency_ms": None,
            "success": None,
            "error": None,
            "completed_at": None
        }

        self.llm_interactions.insert(record)
        logger.debug(f"Logged LLM request: {interaction_id}")

        # Print confirmation
        print(f"📤 LLM Request Logged:")
        print(f"   Interaction ID: {interaction_id}")
        print(f"   Prompt length: {len(prompt)} chars")
        print(f"   Total interactions in DB: {len(self.llm_interactions.all())}")

        return interaction_id

    def log_llm_response(
        self,
        interaction_id: str,
        response: str,
        success: bool,
        latency_ms: float,
        error: str = None,
        parsed_result: Dict[str, Any] = None
    ):
        """
        Update LLM interaction with response

        Args:
            interaction_id: ID from log_llm_request
            response: LLM response
            success: Success status
            latency_ms: Latency
            error: Error message
            parsed_result: Parsed JSON result
        """
        Query_ = Query()
        completed_at = datetime.now().isoformat()

        update_data = {
            "response": response,
            "response_length": len(response) if response else 0,
            "success": success,
            "error": error,
            "latency_ms": latency_ms,
            "completed_at": completed_at,
            "parsed_result": parsed_result
        }

        self.llm_interactions.update(update_data, Query_.interaction_id == interaction_id)
        logger.debug(f"Logged LLM response: {interaction_id} (success={success})")

        # Print confirmation
        status_icon = "✅" if success else "❌"
        print(f"📥 {status_icon} LLM Response Logged:")
        print(f"   Interaction ID: {interaction_id}")
        print(f"   Success: {success}")
        print(f"   Latency: {latency_ms:.2f}ms")
        if response:
            print(f"   Response length: {len(response)} chars")
        if error:
            print(f"   Error: {error}")

    def log_print(self, message: str, level: str = "info", context: Dict[str, Any] = None):
        """
        Log a print/output message

        Args:
            message: The message to log
            level: Log level (info, debug, warning, error)
            context: Additional context
        """
        timestamp = datetime.now().isoformat()

        record = {
            "output_id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "timestamp": timestamp,
            "type": "print",
            "level": level,
            "message": message,
            "context": context or {}
        }

        self.outputs.insert(record)

    def log_json(self, data: Dict[str, Any], label: str = "data", context: Dict[str, Any] = None):
        """
        Log JSON data

        Args:
            data: JSON data to log
            label: Label for this data
            context: Additional context
        """
        timestamp = datetime.now().isoformat()

        record = {
            "output_id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "timestamp": timestamp,
            "type": "json",
            "label": label,
            "data": data,
            "context": context or {}
        }

        self.outputs.insert(record)

    def log_event(self, event_type: str, data: Dict[str, Any] = None):
        """
        Log an event

        Args:
            event_type: Type of event
            data: Event data
        """
        timestamp = datetime.now().isoformat()

        record = {
            "event_id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "timestamp": timestamp,
            "event_type": event_type,
            "data": data or {}
        }

        self.events.insert(record)

    @contextmanager
    def capture_output(self, label: str = "captured_output"):
        """
        Context manager to capture stdout/stderr

        Usage:
            with logger.capture_output("my_operation"):
                print("This will be captured")
        """
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            stdout_content = stdout_capture.getvalue()
            stderr_content = stderr_capture.getvalue()

            if stdout_content:
                self.log_print(stdout_content, level="info", context={
                    "label": label,
                    "stream": "stdout"
                })

            if stderr_content:
                self.log_print(stderr_content, level="error", context={
                    "label": label,
                    "stream": "stderr"
                })

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get summary of this session

        Returns:
            Summary dictionary
        """
        llm_count = len(self.llm_interactions.all())
        output_count = len(self.outputs.all())
        event_count = len(self.events.all())

        llm_success = len([i for i in self.llm_interactions.all() if i.get('success') is True])
        llm_failed = len([i for i in self.llm_interactions.all() if i.get('success') is False])

        latencies = [i.get('latency_ms') for i in self.llm_interactions.all() if i.get('latency_ms')]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        return {
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "session_start": self.session_start,
            "session_end": datetime.now().isoformat(),
            "database_path": self.db_path,
            "counts": {
                "llm_interactions": llm_count,
                "outputs": output_count,
                "events": event_count
            },
            "llm_stats": {
                "total": llm_count,
                "successful": llm_success,
                "failed": llm_failed,
                "success_rate": (llm_success / llm_count * 100) if llm_count > 0 else 0,
                "average_latency_ms": round(avg_latency, 2)
            }
        }

    def close(self):
        """Close the database and log session end"""
        summary = self.get_session_summary()

        self.log_event("session_end", summary)

        logger.info(f"Session ended for workflow {self.workflow_id}")
        logger.info(f"Summary: {summary['counts']}")

        # Print final summary
        print(f"\n{'='*80}")
        print(f"📊 WORKFLOW LOGGER SESSION SUMMARY")
        print(f"{'='*80}")
        print(f"Workflow ID: {self.workflow_id}")
        print(f"Database: {self.db_path}")
        print(f"\nCounts:")
        print(f"   LLM Interactions: {summary['counts']['llm_interactions']}")
        print(f"   Outputs: {summary['counts']['outputs']}")
        print(f"   Events: {summary['counts']['events']}")
        print(f"\nLLM Stats:")
        print(f"   Success Rate: {summary['llm_stats']['success_rate']:.1f}%")
        print(f"   Avg Latency: {summary['llm_stats']['average_latency_ms']:.2f}ms")
        print(f"\n💾 Database saved to: {os.path.abspath(self.db_path)}")
        print(f"{'='*80}\n")

        self.db.close()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


class PrintCapture:
    """
    Helper class to capture all print statements
    Usage: Add to analyzer to automatically capture prints
    """

    def __init__(self, logger: WorkflowInteractionLogger):
        self.logger = logger
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

    def write(self, message):
        """Capture write calls"""
        if message.strip():  # Only log non-empty messages
            self.logger.log_print(message.strip(), level="info")
        # Also write to original stdout
        self.original_stdout.write(message)

    def flush(self):
        """Flush the output"""
        self.original_stdout.flush()


# Global registry to track loggers per workflow
_workflow_loggers: Dict[str, WorkflowInteractionLogger] = {}


def get_workflow_logger(workflow_id: str, base_dir: str = "workflow_logs") -> WorkflowInteractionLogger:
    """
    Get or create a logger for a specific workflow

    Args:
        workflow_id: Workflow ID
        base_dir: Base directory for logs

    Returns:
        WorkflowInteractionLogger instance
    """
    if workflow_id not in _workflow_loggers:
        _workflow_loggers[workflow_id] = WorkflowInteractionLogger(workflow_id, base_dir)

    return _workflow_loggers[workflow_id]


def close_workflow_logger(workflow_id: str):
    """
    Close and remove a workflow logger

    Args:
        workflow_id: Workflow ID
    """
    if workflow_id in _workflow_loggers:
        _workflow_loggers[workflow_id].close()
        del _workflow_loggers[workflow_id]


def close_all_workflow_loggers():
    """Close all active workflow loggers"""
    for workflow_id in list(_workflow_loggers.keys()):
        close_workflow_logger(workflow_id)
