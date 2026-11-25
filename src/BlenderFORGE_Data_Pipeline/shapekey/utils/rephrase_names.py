from transformers import AutoModelForCausalLM, AutoTokenizer
import json
import re
import argparse
from pathlib import Path

def load_model(model_name):
    """Load the tokenizer and model."""
    print(f"Loading model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype="auto",
        device_map="auto"
    )
    print("Model loaded successfully!")
    return tokenizer, model

def extract_list_from_text(text):
    """Extract list from text content, supporting various formats."""
    # Try to find list patterns like ["item1", "item2", ...] or ['item1', 'item2', ...]
    patterns = [
        r'\[([^\]]+)\]',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            list_str = matches[0]
            try:
                result = json.loads(f'[{list_str}]')
                if isinstance(result, list) and len(result) > 0:
                    result = [str(item).strip() for item in result if item]
                    return result
            except:
                # If JSON parsing fails, try manual splitting
                items = re.findall(r'["\']([^"\']+)["\']', list_str)
                if items:
                    return [item.strip() for item in items if item.strip()]
    
    return []

def generate_rephrases(tokenizer, model, keyname, max_retries=3):
    """Generate rephrases for a given shape key name."""
    for attempt in range(max_retries):
        print(f"  Attempt {attempt + 1}/{max_retries}...")
        
        prompt = (f"Give me more than 10 different rephrase of '{keyname}' as shape key names in a list, formatted as [\"name1\", \"name2\", ...]. "
                  "You need to fully understand the initial key. There can be some issue with spacing, for example, there may be no spaces, like brow sad R -> browsadR. "
                  "Only output the list, nothing else.")
        
        messages = [
            {"role": "user", "content": prompt}
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False
        )
        model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

        generated_ids = model.generate(
            **model_inputs,
            max_new_tokens=2048
        )
        output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist() 

        try:
            # Token 151668 closes the thinking block (</think>).
            index = len(output_ids) - output_ids[::-1].index(151668)
        except ValueError:
            index = 0

        thinking_content = tokenizer.decode(output_ids[:index], skip_special_tokens=True).strip("\n")
        content = tokenizer.decode(output_ids[index:], skip_special_tokens=True).strip("\n")

        rephrase_list = extract_list_from_text(content)
        
        if rephrase_list:
            print(f"  ✓ Generated {len(rephrase_list)} rephrases")
            return rephrase_list
        else:
            print(f"  ✗ Failed to extract list, retrying...")
            print(f"  Response: {content[:200]}")
    
    print(f"  ✗ Failed after {max_retries} attempts")
    return []

def main():
    parser = argparse.ArgumentParser(description='Generate rephrases for shape key names')
    parser.add_argument(
        '--input_json',
        type=str,
        default=str(Path(__file__).resolve().parents[1] / 'resources/shapekey_namelist.json'),
        help='Input JSON file with shape key names'
    )
    parser.add_argument(
        '--output_json',
        type=str,
        default=str(Path(__file__).resolve().parents[1] / 'resources/shapekey_rephrases.json'),
        help='Output JSON file for rephrases'
    )
    parser.add_argument(
        '--model_name',
        type=str,
        default='Qwen/Qwen3-14B',
        help='Model name to use'
    )
    parser.add_argument(
        '--start_index',
        type=int,
        default=0,
        help='Start index for processing (for resuming)'
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input_json)
    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist")
        return
    
    with open(input_path, 'r', encoding='utf-8') as f:
        keynames = json.load(f)
    
    print(f"Loaded {len(keynames)} shape key names from {input_path}")
    
    output_path = Path(args.output_json)
    if output_path.exists():
        with open(output_path, 'r', encoding='utf-8') as f:
            results = json.load(f)
        print(f"Loaded existing results with {len(results)} entries")
    else:
        results = {}
    
    tokenizer, model = load_model(args.model_name)
    
    print("\n" + "="*60)
    print("Starting rephrase generation...")
    print("="*60 + "\n")
    
    for i, keyname in enumerate(keynames[args.start_index:], start=args.start_index):
        if keyname in results and results[keyname]:
            print(f"[{i+1}/{len(keynames)}] Skipping '{keyname}' (already processed)")
            continue
        
        print(f"[{i+1}/{len(keynames)}] Processing: '{keyname}'")
        
        rephrases = generate_rephrases(tokenizer, model, keyname)
        results[keyname] = rephrases
        
        # Save results after each key (for recovery)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"  Saved to {output_path}\n")
    
    print("="*60)
    print("Processing complete!")
    print(f"Results saved to: {output_path}")
    print(f"Total entries: {len(results)}")
    print(f"Successful: {sum(1 for v in results.values() if v)}")
    print(f"Failed: {sum(1 for v in results.values() if not v)}")
    print("="*60)

if __name__ == "__main__":
    main()
