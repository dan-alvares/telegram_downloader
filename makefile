.PHONY: build clean

build:
	uv run python -m nuitka \
		--standalone \
		--assume-yes-for-downloads \
		--follow-imports \
		--jobs=4 \
		--include-package=telethon \
		--include-package=asyncio \
		--include-package=dotenv \
		--include-package=typer \
		--include-package=loguru \
		--include-package=rich \
		--include-package=qrcode \
		--include-package=questionary \
		--output-filename=downloader \
		--output-dir=dist \
		--remove-output \
		cli.py
	mv dist/cli.dist dist/build_atual
	chmod +x dist/build_atual/downloader

clean:
	rm -rf dist/