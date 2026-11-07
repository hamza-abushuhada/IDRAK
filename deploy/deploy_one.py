import sys
sys.argv = sys.argv[:2]
import deploy
which = sys.argv[1] if len(sys.argv) > 1 else "api"
url = deploy.deploy(deploy.ROOT / which, deploy.API_PROJECT if which == "api" else deploy.WEB_PROJECT)
print("deployed:", url)
