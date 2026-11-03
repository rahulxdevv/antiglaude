"""Native protobuf TLV decoder for Antigravity SQLite generation metadata (gen_metadata).

Decodes protobuf wire format without requiring external protoc compiler or static proto definitions.
Safely extracts model names, token counts (prompt, output, thinking), response IDs, trace IDs,
session IDs, and context payload breakdown.
"""

from typing import Any, Dict, List, Optional, Tuple, Union


def decode_varint(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Decodes an unsigned varint from bytes starting at offset.
    
    Returns:
        (value, new_offset)
    """
    res = 0
    shift = 0
    idx = offset
    length = len(data)
    while idx < length:
        b = data[idx]
        idx += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            return res, idx
        shift += 7
        if shift > 64:
            break
    return res, idx


def parse_protobuf_wire(data: bytes) -> List[Tuple[int, str, Any]]:
    """Parses raw protobuf wire format into list of (field_number, wire_type, raw_value).
    
    Wire types:
        0: varint
        1: 64-bit fixed
        2: length-delimited (bytes)
        5: 32-bit fixed
    """
    idx = 0
    total = len(data)
    fields = []
    
    while idx < total:
        try:
            key, idx = decode_varint(data, idx)
            field_no = key >> 3
            wire_type = key & 0x7
            
            if field_no == 0:
                break
                
            if wire_type == 0:  # Varint
                val, idx = decode_varint(data, idx)
                fields.append((field_no, "varint", val))
            elif wire_type == 1:  # 64-bit fixed
                if idx + 8 > total:
                    break
                val = data[idx:idx+8]
                idx += 8
                fields.append((field_no, "64bit", val))
            elif wire_type == 2:  # Length-delimited
                length, idx = decode_varint(data, idx)
                if idx + length > total:
                    break
                val = data[idx:idx+length]
                idx += length
                fields.append((field_no, "bytes", val))
            elif wire_type == 5:  # 32-bit fixed
                if idx + 4 > total:
                    break
                val = data[idx:idx+4]
                idx += 4
                fields.append((field_no, "32bit", val))
            else:
                # Unsupported wire type, stop decoding
                break
        except Exception:
            break
            
    return fields


def extract_generation_metadata(data: bytes) -> Dict[str, Any]:
    """Extracts structured generation metadata from Antigravity SQLite gen_metadata blob.
    
    Returns a dictionary containing:
        - model: human-readable name (e.g. 'Gemini 3.8 Flash (High)')
        - model_id: internal model identifier (e.g. 'MODEL_PLACEHOLDER_M318' or 'gemini-3.8-flash-n')
        - backend_model: e.g. 'gemini-3.8-flash-n'
        - prompt_tokens: count of prompt/input tokens
        - output_tokens: count of generated tokens
        - thinking_tokens: count of reasoning/thinking tokens
        - total_tokens: prompt_tokens + output_tokens
        - response_id: server response identifier
        - trace_id: request trace identifier
        - session_id: conversation session identifier
        - trajectory_id: conversation trajectory UUID
        - stop_tokens: list of stop token strings
        - context_sections: list of system instruction sections with byte lengths
    """
    res = {
        "model": "Unknown",
        "model_id": "",
        "backend_model": "",
        "prompt_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "total_tokens": 0,
        "response_id": "",
        "trace_id": "",
        "session_id": "",
        "trajectory_id": "",
        "stop_tokens": [],
        "context_sections": [],
        "has_reasoning": False,
    }
    
    root_fields = parse_protobuf_wire(data)
    
    # Check for direct UUID in field 4 (e.g. request ID)
    for fn, ft, val in root_fields:
        if fn == 4 and ft == "bytes":
            try:
                res["request_uuid"] = val.decode("utf-8", errors="ignore")
            except Exception:
                pass
                
    # Field 1 contains the GenerationContext submessage
    gen_context_bytes = None
    for fn, ft, val in root_fields:
        if fn == 1 and ft == "bytes":
            gen_context_bytes = val
            break
            
    if not gen_context_bytes:
        return res
        
    ctx_fields = parse_protobuf_wire(gen_context_bytes)
    
    for fn, ft, val in ctx_fields:
        if ft == "bytes":
            # Subfield 21: Model display name (e.g. 'Gemini 3.8 Flash (High)')
            if fn == 21:
                try:
                    res["model"] = val.decode("utf-8", errors="ignore")
                except Exception:
                    pass
            # Subfield 19: Backend model name (e.g. 'gemini-3.8-flash-n')
            elif fn == 19:
                try:
                    res["backend_model"] = val.decode("utf-8", errors="ignore")
                    if res["model"] == "Unknown":
                        res["model"] = res["backend_model"]
                except Exception:
                    pass
            # Subfield 20: Repeated key-value metadata (model_enum, trajectory_id, etc.)
            elif fn == 20:
                kv_fields = parse_protobuf_wire(val)
                key = ""
                value = ""
                for kfn, kft, kval in kv_fields:
                    if kfn == 1 and kft == "bytes":
                        key = kval.decode("utf-8", errors="ignore")
                    elif kfn == 2 and kft == "bytes":
                        value = kval.decode("utf-8", errors="ignore")
                if key == "model_enum" and value:
                    res["model_id"] = value
                elif key == "trajectory_id" and value:
                    res["trajectory_id"] = value
            # Subfield 17: Token counts and response metadata
            elif fn == 17:
                f17_fields = parse_protobuf_wire(val)
                for f17_fn, f17_ft, f17_val in f17_fields:
                    if f17_fn == 4 and f17_ft == "bytes":
                        res["trace_id"] = f17_val.decode("utf-8", errors="ignore")
                    elif f17_fn == 2 and f17_ft == "bytes":
                        meta_fields = parse_protobuf_wire(f17_val)
                        for mfn, mft, mval in meta_fields:
                            if mfn == 5 and mft == "varint":
                                res["prompt_tokens"] = mval
                            elif mfn == 2 and mft == "varint":
                                res["output_tokens"] = mval
                            elif mfn == 10 and mft == "varint":
                                res["thinking_tokens"] = mval
                                res["has_reasoning"] = mval > 0
                            elif mfn == 11 and mft == "bytes":
                                res["response_id"] = mval.decode("utf-8", errors="ignore")
                            elif mfn == 8 and mft == "bytes":
                                sess_fields = parse_protobuf_wire(mval)
                                for sfn, sft, sval in sess_fields:
                                    if sfn == 2 and sft == "bytes":
                                        res["session_id"] = sval.decode("utf-8", errors="ignore")
            # Subfield 16: Context sections (e.g. system prompts)
            elif fn == 16:
                sec_fields = parse_protobuf_wire(val)
                sec_name = ""
                sec_len = 0
                for sfn, sft, sval in sec_fields:
                    if sfn == 1 and sft == "bytes":
                        sec_name = sval.decode("utf-8", errors="ignore")
                    elif sfn == 2 and sft == "bytes":
                        sec_len = len(sval)
                if sec_name:
                    res["context_sections"].append({
                        "name": sec_name,
                        "bytes": sec_len,
                    })
            # Subfield 15: Generation config (stop tokens, max tokens)
            elif fn == 15:
                cfg_fields = parse_protobuf_wire(val)
                for cfn, cft, cval in cfg_fields:
                    if cfn == 9 and cft == "bytes":
                        stop_tok = cval.decode("utf-8", errors="ignore")
                        if stop_tok not in res["stop_tokens"]:
                            res["stop_tokens"].append(stop_tok)
                    elif cfn == 2 and cft == "varint":
                        res["max_output_tokens"] = cval

    res["total_tokens"] = res["prompt_tokens"] + res["output_tokens"]
    return res
