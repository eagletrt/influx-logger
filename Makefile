PHONY: init clean

init:
	git config core.hooksPath .githooks
	pip install yapf pylint

clean:
	rm -r */__pycache__ */*/__pycache__
	rm -rf cache
