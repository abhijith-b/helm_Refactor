from ruamel.yaml import YAML

yaml_text = """
application.yml: |
  HOST_ADDRESS: ${HOST_ADDRESS:/10.0.1.86}
  redis:
    nodeAddresses:
      - "redis://redis-cluster-0:6379"
      - "redis://redis-cluster-1:6379"
"""

yaml = YAML()
yaml.preserve_quotes = True
data = yaml.load(yaml_text)

# Mimic processing
import re
content = data['application.yml']
redis_array_pattern = r'([a-zA-Z0-9_]+):\s*(?:\n\s*-\s*["\']?redis://[a-zA-Z0-9.-]+:637[0-9]["\']?)+'
def collapse_array(m):
    lines = [l for l in m.group(0).split('\n') if l.strip('\r\n')]
    key = lines[0]
    nodes = []
    for line in lines[1:]:
        val = line.strip()
        if val.startswith('-'): val = val[1:].strip()
        if val.startswith('"') and val.endswith('"'): val = val[1:-1]
        if val.startswith("'") and val.endswith("'"): val = val[1:-1]
        nodes.append(val)
    return f"{key} " + ",".join(nodes)

content = re.sub(redis_array_pattern, collapse_array, content)

def redis_url_repl(m):
    placeholder = m.group('placeholder')
    full_list = m.group('list')
    default_val = full_list
    env_var_name = placeholder[2:-1] if placeholder else "REDIS_URL"
    return f"{placeholder}{default_val}}}" if placeholder else f"${{{env_var_name}:{default_val}}}"

redis_pattern = r'(?P<placeholder>\${[^:}]+:)?(?P<list>(?:\b(?<!\${)(?![A-Z_]+:)(?:redis://)?[a-zA-Z0-9.-]+:637[0-9](?:,\s*)?)+)(?P<suffix>\})?'
content = re.sub(redis_pattern, redis_url_repl, content)

data['application.yml'] = content

from io import StringIO
stream = StringIO()
yaml.dump(data, stream)
print(stream.getvalue())
