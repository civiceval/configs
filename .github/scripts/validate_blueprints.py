import json
import sys
import os
import yaml # pyyaml

def validate_json_blueprint(file_path, data):
    """Validates a blueprint in the legacy JSON format."""
    errors = []

    # In legacy JSON, id and title are considered mandatory.
    if not isinstance(data.get('id'), str) or not data.get('id'):
        errors.append(f"Missing or invalid 'id' (must be a non-empty string).")
    if not isinstance(data.get('title'), str) or not data.get('title'):
        errors.append(f"Missing or invalid 'title' (must be a non-empty string).")
    
    # Description is optional
    if 'description' in data and not isinstance(data.get('description'), str):
        errors.append(f"Optional 'description' must be a string if present.")

    prompts = data.get('prompts')
    if not isinstance(prompts, list) or not prompts:
        errors.append(f"Missing or empty 'prompts' array.")
    else:
        for i, prompt in enumerate(prompts):
            if not isinstance(prompt, dict):
                errors.append(f"Prompt at index {i} is not a valid object.")
                continue
            
            # Prompt ID is also expected in legacy format
            if not isinstance(prompt.get('id'), str) or not prompt.get('id'):
                errors.append(f"Missing or invalid 'id' in prompt at index {i}.")

            has_prompt_text = 'promptText' in prompt and isinstance(prompt.get('promptText'), str)
            has_messages = 'messages' in prompt and isinstance(prompt.get('messages'), list)

            if not has_prompt_text and not has_messages:
                errors.append(f"Prompt at index {i} (id: {prompt.get('id', 'N/A')}) must contain 'promptText' or 'messages'.")
            
            if 'points' in prompt:
                points = prompt.get('points')
                if not isinstance(points, list):
                    errors.append(f"Optional 'points' in prompt{prompt_id_text} must be a list if present.")
    return errors

def validate_yaml_blueprint(file_path, docs):
    """Validates a blueprint in any of the supported YAML formats."""
    errors = []
    
    # Filter out empty documents that can be created by `---` separators.
    docs = [doc for doc in docs if doc]

    if not docs:
        errors.append("YAML file is empty.")
        return errors

    header = {}
    prompts = []
    
    first_doc = docs[0]

    # Structure 1: Config Header + list of prompts in second doc
    if len(docs) > 1 and isinstance(first_doc, dict) and isinstance(docs[1], list):
        header = first_doc
        prompts = docs[1]
    # Structure 4: Single doc with 'prompts' key
    elif len(docs) == 1 and isinstance(first_doc, dict) and 'prompts' in first_doc:
        header = first_doc
        prompts = header.get('prompts')
        if not isinstance(prompts, list):
             errors.append("The 'prompts' key must contain a list of prompts.")
    # Structure 3: Single doc that is a list of prompts
    elif len(docs) == 1 and isinstance(first_doc, list):
        prompts = first_doc
    # Structure 2: A stream of prompt documents
    elif all(isinstance(d, dict) for d in docs):
        # This could be a header + stream of prompts, or just a stream of prompts.
        # The spec says: if first doc has config keys, it's a header.
        is_header = any(k in first_doc for k in ['id', 'title', 'models', 'system', 'concurrency', 'temperatures', 'evaluationConfig'])
        is_prompt = any(k in first_doc for k in ['prompt', 'messages', 'should', 'ideal'])
        
        # If it has config keys and no prompt keys, it is a header.
        if is_header and not is_prompt:
            header = first_doc
            prompts = docs[1:]
        else: # otherwise, all docs are prompts
            prompts = docs
    else:
        errors.append(
            "Invalid YAML structure. Supported structures are: \n"
            "1. A dictionary (header) followed by '---' and a list of prompts.\n"
            "2. A single YAML document with a 'prompts' key.\n"
            "3. A single YAML document that is a list of prompts.\n"
            "4. A stream of YAML documents, where each document is a prompt."
        )
        # Add detailed logging to understand the failure
        errors.append(f"-> DEBUG: Found {len(docs)} YAML document(s) in the file.")
        for i, doc in enumerate(docs):
            errors.append(f"  - Document {i} type: {type(doc)}, content snippet: {str(doc)[:100]}...")
        return errors

    # --- Prompts Validation ---
    if not isinstance(prompts, list):
        errors.append(f"Could not identify a valid list of prompts.")
    elif not prompts and not header:
        errors.append("Blueprint must contain at least one prompt or a configuration header.")
    else:
        for i, prompt in enumerate(prompts):
            if not isinstance(prompt, dict):
                errors.append(f"Prompt at index {i} is not a valid object/dictionary.")
                continue

            prompt_id_text = f" (prompt id: {prompt.get('id', 'N/A')})"
            
            # Allow aliases
            has_prompt = ('prompt' in prompt and isinstance(prompt.get('prompt'), str)) or \
                         ('promptText' in prompt and isinstance(prompt.get('promptText'), str))
            has_messages = 'messages' in prompt and isinstance(prompt.get('messages'), list)

            if not has_prompt and not has_messages:
                errors.append(f"Prompt at index {i}{prompt_id_text} must contain either 'prompt'/'promptText' or 'messages'.")
            
            # Check all possible rubric keys
            for key in ['should', 'should_not', 'points', 'expect', 'expects', 'expectations']:
                if key in prompt:
                    rubric = prompt.get(key)
                    if not isinstance(rubric, list):
                        errors.append(f"Optional rubric ('{key}') in prompt{prompt_id_text} must be a list if present.")

    return errors

def validate_blueprint(file_path):
    errors = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Determine file type and parse accordingly
            if file_path.endswith('.json'):
                data = json.loads(content)
                errors = validate_json_blueprint(file_path, data)
            elif file_path.endswith(('.yml', '.yaml')):
                docs = list(yaml.safe_load_all(content))
                errors = validate_yaml_blueprint(file_path, docs)
            else:
                print(f"::warning file={file_path}::Skipping file with unrecognized extension.")
                return True # Not a failure, just a skip

    except json.JSONDecodeError as e:
        print(f"::error file={file_path}::Invalid JSON: {e}")
        return False
    except yaml.YAMLError as e:
        print(f"::error file={file_path}::Invalid YAML: {e}")
        return False
    except Exception as e:
        print(f"::error file={file_path}::Could not read or parse file: {e}")
        return False

    if errors:
        for error in errors:
            print(f"::error file={file_path}::{error}")
        return False
    
    print(f"::notice file={file_path}::Validation passed for {os.path.basename(file_path)}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_blueprints.py <file_path1> [<file_path2> ...]")
        sys.exit(1)
    
    all_valid = True
    for file_path_arg in sys.argv[1:]:
        if not os.path.exists(file_path_arg):
            print(f"::error file={file_path_arg}::File not found.")
            all_valid = False
            continue
        if not validate_blueprint(file_path_arg):
            all_valid = False
            
    if not all_valid:
        sys.exit(1) 