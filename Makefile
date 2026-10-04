PHONY: init clean

init:
	git config core.hooksPath .githooks
	python3 -m venv .venv
	.venv/bin/pip install yapf pylint
	.venv/bin/pip install -r requirements.txt

clean:
	rm -r */__pycache__ */*/__pycache__
	rm -rf cache
