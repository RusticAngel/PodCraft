"""Cloud Run deployment helpers.

Provides a Cloud Run service YAML for `gcloud run services replace` and
helpers to build the image tag. Runtime keys should be injected via
Secret Manager (see secret_manager.py) and referenced in the env map.
"""

import os
import json

SERVICE_NAME = "podcraft"
REGION = "us-central1"
ARTIFACT_REPO = "podcraft"


def service_yaml(
    image: str,
    region: str = REGION,
    service_name: str = SERVICE_NAME,
    secret_env_name: str = "GEMINI_API_KEY",
    secret_ref: str = "gemini-api-key:latest",
) -> str:
    """Render a Cloud Run service spec with Secret Manager env injection."""
    env = [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": os.getenv("GOOGLE_CLOUD_PROJECT", "")},
        {"name": "GEMINI_MODEL", "value": os.getenv("GEMINI_MODEL", "gemini-3.5-flash")},
        {"name": "DEFAULT_TTS_VOICE", "value": os.getenv("DEFAULT_TTS_VOICE", "Puck")},
        {"name": "SECONDARY_TTS_VOICE", "value": os.getenv("SECONDARY_TTS_VOICE", "Charon")},
        {"name": "PARALLEL_API_KEY", "value": os.getenv("PARALLEL_API_KEY", "")},
        {"name": secret_env_name, "valueFrom": {"secretKeyRef": {"name": secret_ref, "key": "latest"}}},
    ]
    spec = {
        "apiVersion": "serving.knative.dev/v1",
        "kind": "Service",
        "metadata": {"name": service_name, "namespace": "default", "labels": {"agent": "podcast-production"}},
        "spec": {
            "template": {
                "metadata": {"annotations": {"autoscaling.knative.dev/minScale": "1"}},
                "spec": {
                    "containerConcurrency": 4,
                    "containers": [
                        {
                            "image": image,
                            "env": env,
                            "ports": [{"containerPort": 8080}],
                            "resources": {"limits": {"memory": "512Mi", "cpu": "1"}},
                        }
                    ],
                },
            }
        },
    }
    return json.dumps(spec, indent=2)


def image_tag(project_id: str, region: str = REGION) -> str:
    return f"{region}-docker.pkg.dev/{project_id}/{ARTIFACT_REPO}/{SERVICE_NAME}:latest"


def deploy_cmd(project_id: str, dir_path: str = ".") -> str:
    """Print the canonical Cloud Run deploy command."""
    image = image_tag(project_id, REGION)
    return (
        f"gcloud builds submit --config=cloudbuild.yaml . && "
        f"gcloud run deploy {SERVICE_NAME} --image {image} --region {REGION} "
        f"--set-secrets=GEMINI_API_KEY=gemini-api-key:latest --allow-unauthenticated "
        f"--min-instances=1"
    )


if __name__ == "__main__":
    import sys

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if len(sys.argv) > 1:
        project = sys.argv[1]
    print(service_yaml(image_tag(project) if project else "gcr.io/your-project/podcast-production:latest"))
    print("\n# Deploy command:\n# " + deploy_cmd(project))