.PHONY: test demo compile manifest clean

test:
	python -m unittest discover -s tests -v

demo:
	python scripts/demo.py

compile:
	./scripts/compile.sh

manifest:
	@test -n "$(IMAGE_DIGEST)" || (echo "IMAGE_DIGEST is required" >&2; exit 1)
	@test -n "$(PROVENANCE_DIGEST)" || (echo "PROVENANCE_DIGEST is required" >&2; exit 1)
	python scripts/build_source_manifest.py . \
	  --image-digest "$(IMAGE_DIGEST)" \
	  --provenance-digest "$(PROVENANCE_DIGEST)" \
	  $(if $(SOURCE_URI),--source-uri "$(SOURCE_URI)",) \
	  -o source-manifest.json

clean:
	rm -rf artifacts .cache __pycache__ model/__pycache__ tests/__pycache__ scripts/__pycache__
