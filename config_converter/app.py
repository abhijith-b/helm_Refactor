import os
import re
import json
import xmltodict
from flask import Flask, request, jsonify, render_template
import yaml
from helm_processor import process_helm_values, build_helm_values_from_scratch

app = Flask(__name__)

def flatten_dict(d, parent_key='', sep='.'):
    """Flattens a nested dictionary to a single level dictionary with dot-separated keys."""
    items = []
    if not isinstance(d, dict):
        return {}
    for k, v in d.items():
        if k == "":
            new_key = parent_key
        else:
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def unflatten_dict(d, sep='.'):
    """Unflattens a dot-separated single level dictionary back to a nested dictionary."""
    result = {}
    for k, v in d.items():
        parts = k.split(sep)
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                # Conflict: current[part] is a primitive, convert to dict to allow nesting
                old_val = current[part]
                current[part] = {"": old_val}
            current = current[part]
            
        final_key = parts[-1]
        if final_key in current and isinstance(current[final_key], dict):
            # Conflict: assigning to a key that is already a dictionary
            current[final_key][""] = v
        else:
            current[final_key] = v
    return result

def properties_to_dict(text):
    """Parses standard .properties format text into a flat dictionary."""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            if '=' in line:
                key, val = line.split('=', 1)
                result[key.strip()] = val.strip()
    return result

def dict_to_properties(d):
    """Formats a flat dictionary into .properties format text."""
    lines = []
    for k, v in d.items():
        lines.append(f"{k}={v}")
    return '\n'.join(lines)

def dict_to_xml(d):
    """Converts a dictionary to an XML string."""
    if not isinstance(d, dict) or len(d) != 1:
        d = {'root': d}
    return xmltodict.unparse(d, pretty=True)

def xml_to_dict(text):
    """Parses an XML string to a dictionary."""
    return xmltodict.parse(text)

def add_env_placeholders(flat_dict):
    """
    Transforms flat dict values into Spring Boot style placeholders: ${ENV_VAR_NAME:value}
    Automatically derives the ENV_VAR_NAME from the key (e.g., my.config.value -> MY_CONFIG_VALUE).
    """
    result = {}
    for k, v in flat_dict.items():
        if isinstance(v, str) and v.startswith('${') and v.endswith('}'):
            # Already has a placeholder, keep it as is
            result[k] = v
            continue
        
        # Create env var name from key
        env_var = re.sub(r'[^a-zA-Z0-9]', '_', k).upper()
        # Clean up multiple underscores
        env_var = re.sub(r'_+', '_', env_var).strip('_')
        
        if v is None:
            v_str = ''
        else:
            v_str = str(v)
            
        result[k] = f"${{{env_var}:{v_str}}}"
    return result

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/convert', methods=['POST'])
def convert():
    data = request.json
    input_text = data.get('input_text', '')
    input_format = data.get('input_format', 'yaml')
    output_format = data.get('output_format', 'yaml')
    add_placeholders = data.get('add_placeholders', True)
    
    try:
        # 1. Parse to nested dict
        if input_format == 'yaml':
            parsed = yaml.safe_load(input_text) or {}
        elif input_format == 'json':
            parsed = json.loads(input_text)
        elif input_format == 'xml':
            parsed = xml_to_dict(input_text)
        else:
            flat = properties_to_dict(input_text)
            parsed = unflatten_dict(flat)
            
        flat_dict = flatten_dict(parsed)
            
        # 2. Add placeholders
        if add_placeholders:
            flat_dict = add_env_placeholders(flat_dict)
            
        # 3. Format to output
        nested_dict = unflatten_dict(flat_dict)
        
        if output_format == 'yaml':
            output_text = yaml.dump(nested_dict, default_flow_style=False, sort_keys=False)
        elif output_format == 'json':
            output_text = json.dumps(nested_dict, indent=2)
        elif output_format == 'json_stringified':
            raw_json = json.dumps(nested_dict)
            output_text = json.dumps(raw_json)
        elif output_format == 'xml':
            output_text = dict_to_xml(nested_dict)
        else:
            output_text = dict_to_properties(flat_dict)
            
        return jsonify({'success': True, 'output_text': output_text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/validate', methods=['POST'])
def validate():
    data = request.json
    input_text = data.get('input_text', '')
    input_format = data.get('input_format', 'yaml')
    
    if not input_text.strip():
        return jsonify({'valid': False, 'message': 'Input is empty', 'suggestion': 'Please provide text to validate.'})
    
    try:
        if input_format == 'yaml':
            yaml.safe_load(input_text)
        elif input_format == 'json':
            json.loads(input_text)
        elif input_format == 'xml':
            xmltodict.parse(input_text)
        elif input_format == 'properties':
            properties_to_dict(input_text)
            
        return jsonify({'valid': True, 'message': f'Successfully validated as {input_format.upper()}!'})
    except yaml.YAMLError as e:
        return jsonify({'valid': False, 'message': str(e), 'suggestion': "Check your indentation, colons, and ensure you are not mixing spaces and tabs."})
    except json.JSONDecodeError as e:
        error_msg = f"Line {e.lineno}, Column {e.colno}: {e.msg}"
        return jsonify({'valid': False, 'message': error_msg, 'suggestion': "Ensure all keys and string values are enclosed in double quotes. Check for trailing commas or missing brackets."})
    except Exception as e:
        suggestion = "Review the syntax near the error location."
        if input_format == 'xml':
            suggestion = "Ensure all XML tags are properly closed and there is a single root element."
        return jsonify({'valid': False, 'message': str(e), 'suggestion': suggestion})

@app.route('/api/helm-convert', methods=['POST'])
def helm_convert():
    data = request.json
    input_text = data.get('input_text', '')
    user_inputs = data.get('user_inputs', {})
    
    try:
        output_text = process_helm_values(input_text, user_inputs)
        return jsonify({'success': True, 'output_text': output_text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/build-helm', methods=['POST'])
def build_helm():
    data = request.json
    try:
        output_text = build_helm_values_from_scratch(data)
        return jsonify({'success': True, 'output_text': output_text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("Starting Config Converter on http://localhost:5000")
    app.run(debug=True, port=5000)
