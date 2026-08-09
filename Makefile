.PHONY: install clean install-docker generate uninstall uninstall-docker

.DEFAULT_GOAL := all

SERVICE_FILE = influx-logger.service
DOCKER_SERVICE_FILE = influx-logger-docker.service
CURRENT_USER := $(shell whoami)
WORKING_DIR := $(shell pwd)
PYTHON := $(shell which python3)
SYSTEMD_DIR := $(shell if [ -w /etc/systemd/system ] || [ "$(CURRENT_USER)" = "root" ]; then echo /etc/systemd/system; else echo $(HOME)/.config/systemd/user; fi)
SYSTEMCTL := $(shell if [ -w /etc/systemd/system ] || [ "$(CURRENT_USER)" = "root" ]; then echo systemctl; else echo systemctl --user; fi)

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
	@echo 'ExecStart = $(WORKING_DIR)/tools/script/run.sh' 								>> $(DOCKER_SERVICE_FILE)
	@echo '' 																>> $(DOCKER_SERVICE_FILE)
	@echo '[Install]' 														>> $(DOCKER_SERVICE_FILE)
	@echo 'WantedBy = multi-user.target'									>> $(DOCKER_SERVICE_FILE)

# Install and enable the service with systemd
install: $(SERVICE_FILE)
	@mkdir -p $(SYSTEMD_DIR)
	@install -m 644 $(SERVICE_FILE) $(SYSTEMD_DIR)/$(SERVICE_FILE)
	@$(SYSTEMCTL) daemon-reload 2>/dev/null || true
	@$(SYSTEMCTL) enable $(SERVICE_FILE) 2>/dev/null || true
	@$(SYSTEMCTL) restart $(SERVICE_FILE) 2>/dev/null || true

# Install and enable the service with systemd for docker
install-docker: $(DOCKER_SERVICE_FILE)
	@mkdir -p $(SYSTEMD_DIR)
	@install -m 644 $(DOCKER_SERVICE_FILE) $(SYSTEMD_DIR)/$(DOCKER_SERVICE_FILE)
	@$(SYSTEMCTL) daemon-reload 2>/dev/null || true
	@$(SYSTEMCTL) enable $(DOCKER_SERVICE_FILE) 2>/dev/null || true
	@$(SYSTEMCTL) restart $(DOCKER_SERVICE_FILE) 2>/dev/null || true

# Remove the service file and disable the service with systemd
uninstall: $(SERVICE_FILE)
	@$(SYSTEMCTL) disable $(SERVICE_FILE) 2>/dev/null || true
	@$(SYSTEMCTL) stop $(SERVICE_FILE) 2>/dev/null || true
	@rm -f $(SYSTEMD_DIR)/$(SERVICE_FILE)
	@$(SYSTEMCTL) daemon-reload 2>/dev/null || true

# Remove the service file and disable the service with systemd for docker
uninstall-docker: $(DOCKER_SERVICE_FILE)
	@$(SYSTEMCTL) disable $(DOCKER_SERVICE_FILE) 2>/dev/null || true
	@$(SYSTEMCTL) stop $(DOCKER_SERVICE_FILE) 2>/dev/null || true
	@rm -f $(SYSTEMD_DIR)/$(DOCKER_SERVICE_FILE)
	@$(SYSTEMCTL) daemon-reload 2>/dev/null || true

clean:
	rm -f $(SERVICE_FILE)
	rm -f $(DOCKER_SERVICE_FILE)
