import argparse
import json
import sys

from app.ai.proposer import generate_proposal, UntrustedContentError, ProvenanceError

def main():
    parser = argparse.ArgumentParser(description="Test Proposer manually via Quickstart")
    parser.add_argument("--chunk", required=True, help="Path to chunk JSON file")
    args = parser.parse_args()

    with open(args.chunk, "r") as f:
        chunk_data = json.load(f)

    chunk_id = chunk_data.get("id")
    chunk_text = chunk_data.get("text")

    if not chunk_id or not chunk_text:
        print("Error: chunk JSON must contain 'id' and 'text'")
        sys.exit(1)

    print(f"Generating proposal for chunk: {chunk_id}...")
    try:
        proposal = generate_proposal(chunk_id, chunk_text)
        print("\n--- Proposal Generated Successfully ---")
        print(proposal.model_dump_json(indent=2))
        
        # Verify status is PENDING
        if proposal.status != "PENDING":
            print(f"WARNING: Proposal status is {proposal.status}, expected PENDING!")
    except UntrustedContentError as e:
        print(f"\n[Guardrail Triggered] UntrustedContentError: {e}")
    except ProvenanceError as e:
        print(f"\n[Guardrail Triggered] ProvenanceError: {e}")
    except Exception as e:
        print(f"\nError: {e}")
        
if __name__ == "__main__":
    main()
