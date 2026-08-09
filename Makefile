.PHONY: install clean install-docker generate

.DEFAULT_GOAL := all

SERVICE_FILE = influx-logger.service
DOCKER_SERVICE_FILE = influx-logger-docker.service
CURRENT_USER := $(shell whoami)
WORKING_DIR := $(shell pwd)
PYTHON := $(shell which python3)

all: generate

generate: $(SERVICE_FILE) $(DOCKER_SERVICE_FILE)

$(SERVICE_FILE):
	@echo '[Unit]' 											>  $(SERVICE_FILE)
	@echo 'Description = EagleTRT Influx Logger Service' 	>> $(SERVICE_FILE)
	@echo 'After = network.target'							>> $(SERVICE_FILE)
	@echo '' 												>> $(SERVICE_FILE)
	@echo '[Service]' 										>> $(SERVICE_FILE)
	@echo 'Type = simple' 									>> $(SERVICE_FILE)
	@echo 'User = $(CURRENT_USER)' 							>> $(SERVICE_FILE)
	@echo 'Restart = on-failure' 							>> $(SERVICE_FILE)
	@echo 'WorkingDirectory = $(WORKING_DIR)' 				>> $(SERVICE_FILE)
	@echo 'ExecStart = $(PYTHON) -m src.main' 				>> $(SERVICE_FILE)
	@echo '' 												>> $(SERVICE_FILE)
	@echo '[Install]' 										>> $(SERVICE_FILE)
	@echo 'WantedBy = multi-user.target'					>> $(SERVICE_FILE)

$(DOCKER_SERVICE_FILE):
	@echo '[Unit]' 															>  $(DOCKER_SERVICE_FILE)
	@echo 'Description = EagleTRT Influx Logger Docker Service' 			>> $(DOCKER_SERVICE_FILE)
	@echo 'After = network.target docker.service'							>> $(DOCKER_SERVICE_FILE)
	@echo 'BindsTo = docker.service' 										>> $(DOCKER_SERVICE_FILE)
	@echo 'ReloadPropagatedFrom = docker.service' 							>> $(DOCKER_SERVICE_FILE)
	@echo '' 																>> $(DOCKER_SERVICE_FILE)
	@echo '[Service]' 														>> $(DOCKER_SERVICE_FILE)
	@echo 'Type = simple' 													>> $(DOCKER_SERVICE_FILE)
	@echo 'User = $(CURRENT_USER)' 											>> $(DOCKER_SERVICE_FILE)
	@echo 'Restart = on-failure' 											>> $(DOCKER_SERVICE_FILE)
	@echo 'WorkingDirectory = $(WORKING_DIR)' 								>> $(DOCKER_SERVICE_FILE)
	@echo 'ExecStart = /bin/sh ./tools/script/run.sh' 								>> $(DOCKER_SERVICE_FILE)
	@echo '' 																>> $(DOCKER_SERVICE_FILE)
	@echo '[Install]' 														>> $(DOCKER_SERVICE_FILE)
	@echo 'WantedBy = multi-user.target'									>> $(DOCKER_SERVICE_FILE)

install: $(SERVICE_FILE)
	sudo cp $(SERVICE_FILE) /etc/systemd/system/
	sudo chmod +770 /etc/systemd/system/${SERVICE_FILE}
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE_FILE)

install-docker: $(DOCKER_SERVICE_FILE)
	sudo cp $(DOCKER_SERVICE_FILE) /etc/systemd/system/
	sudo chmod +770 /etc/systemd/system/${DOCKER_SERVICE_FILE}
	sudo systemctl daemon-reload
	sudo systemctl enable $(DOCKER_SERVICE_FILE)

uninstall:
	sudo systemctl disable $(SERVICE_FILE)
	sudo rm -f /etc/systemd/system/$(SERVICE_FILE)
	sudo systemctl daemon-reload

uninstall-docker:
	sudo systemctl disable $(DOCKER_SERVICE_FILE)
	sudo rm -f /etc/systemd/system/$(DOCKER_SERVICE_FILE)
	sudo systemctl daemon-reload

clean:
	rm -f $(SERVICE_FILE)
	rm -f $(DOCKER_SERVICE_FILE)
