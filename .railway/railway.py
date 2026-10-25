from railway_sdk import define_railway, github, project, service
# This repository manages only its own resources in the environment. Other
# repositories export their own partial name.
# See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
PARTIAL = "kapso"
@define_railway
def main(ctx=None):
    kapso = service(
        "kapso",
        source=github("lupydev/kapso", **{ "branch": "main", "checkSuites": True }),
        build={ "buildEnvironment": "V3", "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
        healthcheck="/health",
        healthcheckTimeout=60,
        preDeploy="python -m app.seed",
        replicas={ "us-east4-eqdc4a": 1 },
    )
    return project("kapso", variables={"managed": False}, resources=[kapso])
