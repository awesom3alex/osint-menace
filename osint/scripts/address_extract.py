"""Bounded offline libpostal worker. Original input is never overwritten."""
import json
import resource
import sys

if __name__ == '__main__':
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(40,40))
    from postal.expand import expand_address
    from postal.parser import parse_address
    original=sys.stdin.buffer.read(4000).decode('utf-8')
    components=[dict(value=value,label=label) for value,label in parse_address(original)]
    variants=list(dict.fromkeys(expand_address(original)))
    print(json.dumps(dict(components=components,normalized_suggestions=variants[:10],suggestions_truncated=len(variants)>10),ensure_ascii=False))
