import re
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import PreservedScalarString

def get_config_string_processor(base_vars, constructed_env_vars):
    def process_config_string(content):
        if not isinstance(content, str):
            return content
            
        # Regex for JDBC
        jdbc_pattern = r'(?P<placeholder>\${[^:}]+:)?(?P<jdbc>jdbc:(?P<type>\w+)://(?P<ip>[^:/]+):(?P<port>\d+)/(?P<db>\w+))(?P<suffix>\})?'
        
        def jdbc_repl(m):
            full_match = m.group(0)
            placeholder = m.group('placeholder')
            jdbc_full = m.group('jdbc')
            db_type = m.group('type')
            ip = m.group('ip')
            port = m.group('port')
            db_name = m.group('db')
            
            if not base_vars['DB_TYPE']: base_vars['DB_TYPE'] = db_type
            if not base_vars['DB_IP']: base_vars['DB_IP'] = ip
            if not base_vars['DB_PORT']: base_vars['DB_PORT'] = port
            
            if placeholder:
                env_var_name = placeholder[2:-1]
                result = f"{placeholder}{jdbc_full}}}"
            else:
                env_var_name = f"{db_name.upper()}_DATASOURCE_URL"
                result = f"${{{env_var_name}:{jdbc_full}}}"
                
            constructed_env_vars[env_var_name] = f"jdbc:$(DB_TYPE)://$(DB_IP):$(DB_PORT)/{db_name}"
            return result

        content = re.sub(jdbc_pattern, jdbc_repl, content)

        def host_address_repl(m):
            placeholder = m.group('placeholder')
            ip = m.group('ip')
            if not placeholder:
                if 'HOST_ADDRESS' not in base_vars:
                    base_vars['HOST_ADDRESS'] = ip.strip('/')
                constructed_env_vars['HOST_ADDRESS'] = base_vars['HOST_ADDRESS']
                return f"HOST_ADDRESS: ${{HOST_ADDRESS:{ip}}}"
            return m.group(0)

        content = re.sub(r'HOST_ADDRESS:\s*(?P<placeholder>\${HOST_ADDRESS:)?(?P<ip>[0-9a-zA-Z./-]+)\}?', host_address_repl, content)

        def kafka_repl(m):
            placeholder = m.group('placeholder')
            full_list = m.group('list')
            
            parts = re.findall(r'([a-zA-Z0-9.-]+):(\d+)', full_list)
            ips = [p[0] for p in parts]
            ports = [p[1] for p in parts]
            
            if not base_vars['KAFKA_IP']: base_vars['KAFKA_IP'] = ','.join(ips)
            if not base_vars['KAFKA_PORT']: base_vars['KAFKA_PORT'] = ports[0] if ports else '9092'
            
            user_ips = [i.strip() for i in base_vars['KAFKA_IP'].split(',')]
            
            if ',' in full_list:
                env_val = ','.join([f"{ip}:$(KAFKA_PORT)" for ip in user_ips])
                default_val = ','.join([f"{ip}:{base_vars['KAFKA_PORT']}" for ip in user_ips])
                default_env_var = "SPRING_KAFKA_BOOTSTRAP_SERVERS"
            else:
                if len(user_ips) > 1:
                    constructed_env_vars["KAFKA_HOST"] = user_ips[0]
                    env_val = "$(KAFKA_HOST):$(KAFKA_PORT)"
                    default_val = f"{user_ips[0]}:{base_vars['KAFKA_PORT']}"
                else:
                    env_val = "$(KAFKA_IP):$(KAFKA_PORT)"
                    default_val = f"{base_vars['KAFKA_IP']}:{base_vars['KAFKA_PORT']}"
                default_env_var = "KAFKA_HOST_URL"
                
            env_var_name = placeholder[2:-1] if placeholder else default_env_var
            constructed_env_vars[env_var_name] = env_val
            
            return f"{placeholder}{default_val}}}" if placeholder else f"${{{env_var_name}:{default_val}}}"
            
        kafka_pattern = r'(?P<placeholder>\${[^:}]+:)?(?P<list>(?:\b(?<!\${)(?![A-Z_]+:)[a-zA-Z0-9.-]+:909[2-3](?:,\s*)?)+)(?P<suffix>\})?'
        content = re.sub(kafka_pattern, kafka_repl, content)

        def redis_url_repl(m):
            placeholder = m.group('placeholder')
            full_list = m.group('list')
            
            parts = re.findall(r'(?:redis://)?([a-zA-Z0-9.-]+):(\d+)', full_list)
            ips = [p[0] for p in parts]
            ports = [p[1] for p in parts]
            
            if not base_vars['REDIS_IP']: base_vars['REDIS_IP'] = ','.join(ips)
            if not base_vars['REDIS_PORT']: base_vars['REDIS_PORT'] = ports[0] if ports else '6379'
            
            user_ips = [i.strip() for i in base_vars['REDIS_IP'].split(',')]
            
            has_prefix = 'redis://' in full_list
            prefix = 'redis://' if has_prefix else ''
            
            if ',' in full_list:
                env_val = ','.join([f"{prefix}{ip}:$(REDIS_PORT)" for ip in user_ips])
                default_val = ','.join([f"{prefix}{ip}:{base_vars['REDIS_PORT']}" for ip in user_ips])
                default_env_var = "REDIS_URL"
            else:
                if len(user_ips) > 1:
                    constructed_env_vars["REDIS_HOST"] = user_ips[0]
                    env_val = f"{prefix}$(REDIS_HOST):$(REDIS_PORT)"
                    default_val = f"{prefix}{user_ips[0]}:{base_vars['REDIS_PORT']}"
                else:
                    env_val = f"{prefix}$(REDIS_IP):$(REDIS_PORT)"
                    default_val = f"{prefix}{base_vars['REDIS_IP']}:{base_vars['REDIS_PORT']}"
                default_env_var = "REDIS_HOST_URL"
                
            env_var_name = placeholder[2:-1] if placeholder else default_env_var
            constructed_env_vars[env_var_name] = env_val
            
            return f"{placeholder}{default_val}}}" if placeholder else f"${{{env_var_name}:{default_val}}}"
            
        redis_pattern = r'(?P<placeholder>\${[^:}]+:)?(?P<list>(?:\b(?<!\${)(?![A-Z_]+:)(?:redis://)?[a-zA-Z0-9.-]+:637[0-9](?:,\s*)?)+)(?P<suffix>\})?'
        content = re.sub(redis_pattern, redis_url_repl, content)

        def file_path_repl(m):
            placeholder = m.group('placeholder')
            full_path = m.group('path')
            
            parts = full_path.split('/')
            filename = parts[-1]
            
            if not filename:
                return m.group(0)
                
            replacement = f"$(BASE_PATH)/{filename}"
            
            if placeholder:
                env_var_name = placeholder[2:-1]
                constructed_env_vars[env_var_name] = replacement
                return f"{placeholder}{replacement}}}"
            else:
                env_var_name = re.sub(r'[^A-Z0-9]', '_', filename.upper()) + "_PATH"
                constructed_env_vars[env_var_name] = replacement
                return f"${{{env_var_name}:{replacement}}}"
                
        file_path_pattern = r'(?P<placeholder>\${[^:}]+:)?(?P<path>/(?:opt|app)(?:/[a-zA-Z0-9_.-]+)*(/[a-zA-Z0-9_.-]+))(?P<suffix>\})?'
        content = re.sub(file_path_pattern, file_path_repl, content)

        return content
    return process_config_string

def build_extra_envs(data, base_vars, constructed_env_vars):
    if 'extraEnv' not in data or not isinstance(data['extraEnv'], list):
        data['extraEnv'] = []

    # Filter out base_vars from existing extraEnv so we can force them to the top
    filtered_extra_env = []
    existing_envs = {}
    for item in data['extraEnv']:
        if isinstance(item, dict) and 'name' in item:
            if item['name'] in base_vars:
                continue # Remove it from the current position
            filtered_extra_env.append(item)
            existing_envs[item['name']] = item
        else:
            filtered_extra_env.append(item)

    data['extraEnv'] = filtered_extra_env

    # Add or update constructed_env_vars
    new_constructed = []
    for k, v in constructed_env_vars.items():
        if k in existing_envs:
            existing_envs[k]['value'] = v
        else:
            new_constructed.append({'name': k, 'value': v})

    # Prepend new constructed vars
    for env in reversed(new_constructed):
        data['extraEnv'].insert(0, env)

    # Prepend base_vars so they are at the absolute top
    base_envs = [{'name': k, 'value': str(v)} for k, v in base_vars.items() if v]
    for env in reversed(base_envs):
        data['extraEnv'].insert(0, env)

def process_helm_values(yaml_text, user_inputs):
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    
    try:
        data = yaml.load(yaml_text)
    except Exception as e:
        raise ValueError(f"Failed to parse YAML: {str(e)}")

    if not isinstance(data, dict):
        raise ValueError("YAML root is not a dictionary.")

    base_vars = {
        'DB_TYPE': user_inputs.get('DB_TYPE', ''),
        'DB_IP': user_inputs.get('DB_IP', ''),
        'DB_PORT': user_inputs.get('DB_PORT', ''),
        'REDIS_IP': user_inputs.get('REDIS_IP', ''),
        'REDIS_PORT': user_inputs.get('REDIS_PORT', ''),
        'KAFKA_IP': user_inputs.get('KAFKA_IP', ''),
        'KAFKA_PORT': user_inputs.get('KAFKA_PORT', ''),
        'BASE_PATH': user_inputs.get('BASE_PATH', '/app/config'),
        'HOST_ADDRESS': user_inputs.get('HOST_ADDRESS', '')
    }

    constructed_env_vars = {}
    process_config_string = get_config_string_processor(base_vars, constructed_env_vars)

    if 'configFiles' in data and 'files' in data['configFiles']:
        files_dict = data['configFiles']['files']
        for filename, content in files_dict.items():
            if isinstance(content, str):
                files_dict[filename] = process_config_string(content)
                
    build_extra_envs(data, base_vars, constructed_env_vars)

    from io import StringIO
    stream = StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()

def build_helm_values_from_scratch(params):
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    
    service_name = params.get('serviceName', 'my-service')
    image_tag = params.get('imageTag', '1.0.0')
    replica_count = int(params.get('replicaCount', 0))
    persistence_enabled = params.get('persistenceEnabled', False)
    ingress_enabled = params.get('ingressEnabled', False)
    files = params.get('files', [])
    resources_req_cpu = params.get('resourcesReqCpu', '500m')
    resources_req_mem = params.get('resourcesReqMem', '1Gi')
    resources_lim_cpu = params.get('resourcesLimCpu', '1500m')
    resources_lim_mem = params.get('resourcesLimMem', '1Gi')
    rollout_strategy = params.get('rolloutStrategy', 'None')
    rollout_canary = params.get('rolloutCanary', {})
    
    data = {
        'fullnameOverride': service_name,
        'replicaCount': replica_count,
        'image': {
            'repository': f"192.168.120.55:8084/pcc/{service_name}",
            'tag': image_tag,
            'pullPolicy': 'Always',
            'pullSecrets': [{'name': 'jcr-credentials'}]
        },
        'service': {
            'type': 'ClusterIP',
            'ports': [
                {
                    'name': 'http',
                    'port': 8080,
                    'targetPort': 8080,
                    'protocol': 'TCP'
                }
            ]
        }
    }
    
    if ingress_enabled:
        data['ingress'] = {
            'enabled': True,
            'hosts': [{'host': f"{service_name}.local", 'paths': [{'path': '/', 'pathType': 'ImplementationSpecific'}]}]
        }
        
    if persistence_enabled:
        data['persistence'] = {
            'enabled': True,
            'mountPath': '/app/data',
            'size': '512Mi',
            'storageClass': 'local-path',
            'accessMode': 'ReadWriteOnce'
        }
        
    data['probes'] = {
        'liveness': {'enabled': False},
        'readiness': {'enabled': False}
    }
    
    data['resources'] = {
        'requests': {'cpu': resources_req_cpu, 'memory': resources_req_mem},
        'limits': {'cpu': resources_lim_cpu, 'memory': resources_lim_mem}
    }
    
    data['hpa'] = {'enabled': False}
    
    if rollout_strategy == 'Canary':
        data['rollout'] = {
            'enabled': True,
            'strategy': 'canary',
            'canary': {
                'istio': {
                    'virtualServiceName': rollout_canary.get('virtualServiceName', 'pcrf-api'),
                    'routeName': rollout_canary.get('routeName', service_name)
                },
                'steps': [
                    {'setWeight': 5},
                    {'pause': {'duration': '10m'}},
                    {'analysis': {'templates': [{'templateName': 'pcrf-http-success-rate'}]}},
                    {'setWeight': 10},
                    {'pause': {'duration': '10m'}},
                    {'analysis': {'templates': [{'templateName': 'pcrf-http-success-rate'}]}},
                    {'setWeight': 25},
                    {'pause': {'duration': '15m'}},
                    {'analysis': {'templates': [{'templateName': 'pcrf-http-success-rate'}]}},
                    {'setWeight': 50},
                    {'pause': {}},
                    {'setWeight': 100}
                ]
            }
        }
    elif rollout_strategy == 'Blue-Green':
        data['rollout'] = {
            'enabled': True,
            'strategy': 'blueGreen',
            'blueGreen': {
                'activeService': service_name,
                'previewService': f"{service_name}-preview",
                'autoPromotionEnabled': False
            }
        }

    base_vars = {
        'DB_TYPE': 'mariaDb',
        'DB_IP': '10.0.1.15',
        'DB_PORT': '3306',
        'REDIS_IP': 'redis-cluster-0.redis-cluster-headless.redis.svc.cluster.local,redis-cluster-1.redis-cluster-headless.redis.svc.cluster.local,redis-cluster-2.redis-cluster-headless.redis.svc.cluster.local',
        'REDIS_PORT': '6379',
        'KAFKA_IP': 'pcrf-kafka-kafka-bootstrap.kafka.svc.cluster.local',
        'KAFKA_PORT': '9092',
        'BASE_PATH': '/app/config',
        'HOST_ADDRESS': '10.0.1.86'
    }

    constructed_env_vars = {}
    process_config_string = get_config_string_processor(base_vars, constructed_env_vars)

    if files:
        data['configFiles'] = {
            'mountPath': '/app/config',
            'writable': True,
            'files': {}
        }
        for file_obj in files:
            filename = file_obj['filename']
            content = file_obj['content']
            
            # Add implicit _PATH variable for this file
            env_var_name = re.sub(r'[^A-Z0-9]', '_', filename.upper()) + "_PATH"
            constructed_env_vars[env_var_name] = f"$(BASE_PATH)/{filename}"
            
            processed_content = process_config_string(content)
            # Normalize line endings to \n to ensure block scalar formatting works properly
            processed_content = processed_content.replace('\r\n', '\n')
            data['configFiles']['files'][filename] = PreservedScalarString(processed_content)
            
    build_extra_envs(data, base_vars, constructed_env_vars)

    from io import StringIO
    stream = StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()
