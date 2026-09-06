import os
import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

def test_deploy_script_scaffolding_exists():
    deploy_dir = REPO_ROOT / "deploy"
    assert deploy_dir.is_dir()
    env_example = deploy_dir / "cloud-run.env.example"
    assert env_example.is_file()

def test_dockerfile_complies_with_production_constraints():
    dockerfile_path = REPO_ROOT / "Dockerfile"
    assert dockerfile_path.is_file(), "Dockerfile must exist"
    content = dockerfile_path.read_text(encoding="utf-8")
    
    # Must use python 3.12
    assert "python:3.12" in content
    # Zero Node: No node or npm installed in container
    assert "npm" not in content and "nodejs" not in content
    # Must run as non-root user
    assert "USER " in content
    # Must bind to $PORT or default 8080 and 0.0.0.0
    assert "PORT" in content
    assert "0.0.0.0" in content

def test_dockerignore_prohibits_sensitive_and_dev_paths():
    dockerignore_path = REPO_ROOT / ".dockerignore"
    assert dockerignore_path.is_file(), ".dockerignore must exist"
    content = dockerignore_path.read_text(encoding="utf-8")
    patterns = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
    
    # Must exclude virtualenvs, local env files, git, tests, and data archives/databases
    assert any(".env" in p for p in patterns)
    assert any(".venv" in p for p in patterns)
    assert any(".git" in p for p in patterns)
    assert any("data" in p for p in patterns)
    assert any("tests" in p for p in patterns)
    assert any("*.db" in p or "data/" in p for p in patterns)

def test_deploy_script_carries_required_challenge_label():
    deploy_sh = REPO_ROOT / "deploy" / "deploy.sh"
    assert deploy_sh.is_file(), "deploy/deploy.sh must exist"
    content = deploy_sh.read_text(encoding="utf-8")
    assert "dev-tutorial=cloud-run-ai-challenge" in content, "Deploy script must include required challenge label"

def test_deploy_script_verifies_healthz_and_prints_service_url():
    deploy_sh = REPO_ROOT / "deploy" / "deploy.sh"
    assert deploy_sh.is_file(), "deploy/deploy.sh must exist"
    content = deploy_sh.read_text(encoding="utf-8")
    assert "/healthz" in content, "Deploy script must verify /healthz"
    assert "SERVICE_URL" in content, "Deploy script must export or output SERVICE_URL"

def test_scheduler_script_configures_oidc_jobs():
    scheduler_sh = REPO_ROOT / "deploy" / "scheduler.sh"
    assert scheduler_sh.is_file(), "deploy/scheduler.sh must exist"
    content = scheduler_sh.read_text(encoding="utf-8")
    assert "roles/run.invoker" in content, "Scheduler script must bind run.invoker"
    assert "oidc-service-account-email" in content, "Scheduler script must use OIDC service account"
    assert "/api/poll-feeds" in content, "Scheduler script must schedule feed polling"
    assert "/api/consolidate" in content, "Scheduler script must schedule consolidation"
