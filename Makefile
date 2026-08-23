.PHONY: install clean generate uninstall proto

.DEFAULT_GOAL := all

SERVICE_FILE = influx-logger.service
PROTO_DIR = external/serializer/proto
GENERATED_DIR = .generated
CURRENT_USER := $(shell whoami)
WORKING_DIR := $(shell pwd)
PYTHON := $(shell which python3)
SYSTEMD_DIR := $(shell if [ -w /etc/systemd/system ] || [ "$(CURRENT_USER)" = "root" ]; then echo /etc/systemd/system; else echo $(HOME)/.config/systemd/user; fi)
SYSTEMCTL := $(shell if [ -w /etc/systemd/system ] || [ "$(CURRENT_USER)" = "root" ]; then echo systemctl; else echo systemctl --user; fi)

all: proto generate

generate: $(SERVICE_FILE) $(DOCKER_SERVICE_FILE)

# Generate the protobuf modules of the query protocol from the telemetry-serializers submodule
proto:
	@if [ ! -d "$(PROTO_DIR)" ]; then \
		echo "$(PROTO_DIR) not found: run 'git submodule update --init --recursive'"; \
		exit 1; \
	fi
	@mkdir -p $(GENERATED_DIR)
	@$(PYTHON) -m grpc_tools.protoc -I $(PROTO_DIR) --python_out=$(GENERATED_DIR) $$(find $(PROTO_DIR) -name '*.proto')
	@echo 'Generated the protobuf modules in $(GENERATED_DIR)'

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

# Install and enable the service with systemd
install: $(SERVICE_FILE)
	@mkdir -p $(SYSTEMD_DIR)
	@install -m 644 $(SERVICE_FILE) $(SYSTEMD_DIR)/$(SERVICE_FILE)
	@$(SYSTEMCTL) daemon-reload 2>/dev/null || true
	@$(SYSTEMCTL) enable $(SERVICE_FILE) 2>/dev/null || true
	@$(SYSTEMCTL) restart $(SERVICE_FILE) 2>/dev/null || true

# Remove the service file and disable the service with systemd
uninstall: $(SERVICE_FILE)
	@$(SYSTEMCTL) disable $(SERVICE_FILE) 2>/dev/null || true
	@$(SYSTEMCTL) stop $(SERVICE_FILE) 2>/dev/null || true
	@rm -f $(SYSTEMD_DIR)/$(SERVICE_FILE)
	@$(SYSTEMCTL) daemon-reload 2>/dev/null || true

clean:
	rm -f $(SERVICE_FILE)
	rm -rf $(GENERATED_DIR)
