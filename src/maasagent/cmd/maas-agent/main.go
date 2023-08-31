package main

/*
	Copyright 2023 Canonical Ltd.  This software is licensed under the
	GNU Affero General Public License version 3 (see the file LICENSE).
*/

import (
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	backoff "github.com/cenkalti/backoff/v4"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/converter"
	"gopkg.in/yaml.v3"
	wf "maas.io/core/src/maasagent/internal/workflow"
	wflog "maas.io/core/src/maasagent/internal/workflow/log"
	"maas.io/core/src/maasagent/internal/workflow/worker"
	"maas.io/core/src/maasagent/pkg/workflow/codec"
)

const (
	TemporalPort = 5271
)

// config represents a neccessary set of configuration options for MAAS Agent
type config struct {
	MAASUUID    string   `yaml:"maas_uuid"`
	SystemID    string   `yaml:"system_id"`
	Secret      string   `yaml:"secret"`
	Controllers []string `yaml:"controllers,flow"`
}

func Run() int {
	zerolog.SetGlobalLevel(zerolog.InfoLevel)

	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})

	if envLogLevel, ok := os.LookupEnv("LOG_LEVEL"); ok {
		if logLevel, err := zerolog.ParseLevel(envLogLevel); err != nil {
			log.Warn().Str("LOG_LEVEL", envLogLevel).Msg("Unknown log level, defaulting to INFO")
		} else {
			zerolog.SetGlobalLevel(logLevel)
		}
	}

	cfg, err := getConfig()
	if err != nil {
		log.Error().Err(err).Send()
		return 1
	}

	// Encryption Codec required for Temporal Workflow's payload encoding
	codec, err := codec.NewEncryptionCodec([]byte(cfg.Secret))
	if err != nil {
		log.Error().Err(err).Msg("Encryption codec setup failed")
		return 1
	}

	clientBackoff := backoff.NewExponentialBackOff()
	clientBackoff.MaxElapsedTime = 60 * time.Second

	client, err := backoff.RetryWithData(
		func() (client.Client, error) {
			return client.Dial(client.Options{
				// TODO: fallback retry if Controllers[0] is unavailable
				HostPort: fmt.Sprintf("%s:%d", cfg.Controllers[0], TemporalPort),
				Logger:   wflog.NewZerologAdapter(log.Logger),
				DataConverter: converter.NewCodecDataConverter(
					converter.GetDefaultDataConverter(),
					codec,
				),
			})
		}, clientBackoff,
	)

	if err != nil {
		log.Error().Err(err).Msg("Temporal client error")
		return 1
	}

	workerPool := worker.NewWorkerPool(cfg.SystemID, client,
		worker.WithAllowedWorkflows(map[string]interface{}{
			"check_ip":              wf.CheckIP,
			"commission":            wf.Commission,
			"deploy":                wf.Deploy,
			"deployed_os_workflow":  wf.DeployedOS,
			"ephemeral_os_workflow": wf.EphemeralOS,
			"power_on":              wf.PowerOn,
			"power_off":             wf.PowerOff,
			"power_query":           wf.PowerQuery,
			"power_cycle":           wf.PowerCycle,
		}), worker.WithAllowedActivities(map[string]interface{}{
			"switch_boot_order": wf.SwitchBootOrderActivity,
			"power":             wf.PowerActivity,
		}))

	workerPoolBackoff := backoff.NewExponentialBackOff()
	workerPoolBackoff.MaxElapsedTime = 60 * time.Second

	err = backoff.Retry(workerPool.Start, workerPoolBackoff)
	if err != nil {
		log.Error().Err(err).Msg("Temporal worker pool failure")
		return 1
	}

	log.Info().Msg("Service MAAS Agent started")

	sigC := make(chan os.Signal, 2)

	signal.Notify(sigC, syscall.SIGTERM, syscall.SIGINT)

	select {
	case err := <-workerPool.Error():
		log.Fatal().Err(err).Msg("Temporal worker pool failure")
		return 1
	case <-sigC:
		return 0
	}
}

// getConfig reads MAAS Agent YAML configuration file
// TODO: agent.yaml config is generated by rackd, however this behaviour
// should be changed when MAAS Agent will be a standalone service, not managed
// by the Rack Controller.
func getConfig() (*config, error) {
	fname := os.Getenv("MAAS_AGENT_CONFIG")
	if fname == "" {
		fname = "/etc/maas/agent.yaml"
	}

	data, err := os.ReadFile(filepath.Clean(fname))
	if err != nil {
		return nil, fmt.Errorf("configuration error: %w", err)
	}

	cfg := &config{}

	err = yaml.Unmarshal([]byte(data), cfg)
	if err != nil {
		return nil, fmt.Errorf("configuration error: %w", err)
	}

	return cfg, nil
}

func main() {
	os.Exit(Run())
}
