"""Run selected upstream CLIs with local public-suffix data and fixed CLI arguments."""

import sys


def main():
    tool = sys.argv[1]
    sys.argv = [tool, *sys.argv[2:]]
    # Upstream uses tldextract for parsing. Avoid its first-run PSL download;
    # parsing does not require disclosing the target or contacting another service.
    import tldextract
    import tldextract.tldextract

    local = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
    tldextract.extract = local
    tldextract.tldextract.TLD_EXTRACTOR = local
    if tool == "waymore":
        from waymore.waymore import main as run
    elif tool == "theharvester":
        from theHarvester.theHarvester import main as run
    else:
        raise ValueError("Unsupported upstream CLI.")
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
