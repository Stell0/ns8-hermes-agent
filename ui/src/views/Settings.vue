<!--
  Copyright (C) 2023 Nethesis S.r.l.
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <div>
    <cv-grid fullWidth>
      <cv-row>
        <cv-column class="page-title">
          <h2>{{ $t("settings.title") }}</h2>
        </cv-column>
      </cv-row>
      <cv-row v-if="error.getConfiguration">
        <cv-column>
          <NsInlineNotification
            kind="error"
            :title="$t('action.get-configuration')"
            :description="error.getConfiguration"
            :showCloseButton="false"
          />
        </cv-column>
      </cv-row>
      <cv-row>
        <cv-column>
          <cv-tile light class="section-tile">
            <cv-grid class="no-padding">
              <cv-row>
                <cv-column :md="6" :max="8">
                  <h4 class="section-title">
                    {{ $t("settings.openviking_title") }}
                  </h4>
                  <p class="section-description">
                    {{ $t("settings.openviking_description") }}
                  </p>
                </cv-column>
              </cv-row>
              <cv-row>
                <cv-column :md="4" :max="8">
                  <cv-select
                    v-model="openviking.embedding.provider"
                    :label="$t('settings.embedding_provider')"
                    :invalid-message="error.embeddingProvider"
                    :disabled="loading.getConfiguration || loading.configureModule"
                    ref="embeddingProvider"
                    class="mg-bottom-lg"
                  >
                    <cv-select-option value="">
                      {{ $t("settings.embedding_provider_none") }}
                    </cv-select-option>
                    <cv-select-option
                      v-for="provider in embeddingProviders"
                      :key="provider.value"
                      :value="provider.value"
                    >
                      {{ provider.label }}
                    </cv-select-option>
                  </cv-select>
                </cv-column>
                <cv-column :md="4" :max="8">
                  <NsTextInput
                    v-model.trim="openviking.embedding.api_key"
                    :label="$t('settings.embedding_api_key')"
                    :placeholder="$t('settings.embedding_api_key_placeholder')"
                    :invalid-message="error.embeddingApiKey"
                    :disabled="loading.getConfiguration || loading.configureModule"
                    ref="embeddingApiKey"
                    type="password"
                  />
                  <p class="field-helper">
                    {{ embeddingApiKeyHelper }}
                  </p>
                </cv-column>
              </cv-row>
              <cv-row v-if="showEmbeddingChangeWarning">
                <cv-column>
                  <NsInlineNotification
                    kind="warning"
                    :title="$t('settings.embedding_warning_title')"
                    :description="$t('settings.embedding_warning_description')"
                    :showCloseButton="false"
                  />
                </cv-column>
              </cv-row>
            </cv-grid>
          </cv-tile>
        </cv-column>
      </cv-row>
      <cv-row>
        <cv-column>
          <cv-tile light>
            <cv-grid class="no-padding">
              <cv-row class="toolbar-row">
                <cv-column :md="6" :max="8">
                  <h4 class="section-title">
                    {{ $t("settings.agents_title") }}
                  </h4>
                  <p class="section-description">
                    {{ $t("settings.agents_description") }}
                  </p>
                </cv-column>
                <cv-column :md="2" :max="8" class="toolbar-actions">
                  <NsButton
                    kind="secondary"
                    :icon="Add20"
                    :disabled="
                      loading.getConfiguration || loading.configureModule
                    "
                    @click="showCreateAgentModal"
                  >
                    {{ $t("settings.create_agent") }}
                  </NsButton>
                </cv-column>
              </cv-row>
              <cv-row>
                <cv-column>
                  <cv-skeleton-text
                    v-if="loading.getConfiguration"
                    :paragraph="true"
                    :line-count="6"
                  ></cv-skeleton-text>
                  <NsEmptyState
                    v-else-if="!visibleAgents.length"
                    :title="$t('settings.no_agents')"
                  ></NsEmptyState>
                  <cv-structured-list v-else>
                    <template slot="headings">
                      <cv-structured-list-heading>
                        {{ $t("settings.agent_name") }}
                      </cv-structured-list-heading>
                      <cv-structured-list-heading>
                        {{ $t("settings.role") }}
                      </cv-structured-list-heading>
                      <cv-structured-list-heading>
                        {{ $t("settings.status") }}
                      </cv-structured-list-heading>
                      <cv-structured-list-heading>
                        {{ $t("settings.actions") }}
                      </cv-structured-list-heading>
                    </template>
                    <template slot="items">
                      <cv-structured-list-item
                        v-for="agentData in visibleAgents"
                        :key="agentData.id"
                      >
                        <cv-structured-list-data class="break-word">
                          {{ agentData.name }}
                          <p
                            v-if="agentData.use_default_gateway_for_llm"
                            class="gateway-flag"
                          >
                            {{ $t("settings.use_default_gateway_for_llm") }}
                          </p>
                        </cv-structured-list-data>
                        <cv-structured-list-data>
                          {{ roleLabel(agentData.role) }}
                        </cv-structured-list-data>
                        <cv-structured-list-data>
                          <cv-tag
                            :kind="statusKind(agentData.status)"
                            size="sm"
                            :label="statusLabel(agentData.status)"
                            class="no-margin"
                          ></cv-tag>
                        </cv-structured-list-data>
                        <cv-structured-list-data
                          class="table-overflow-menu-cell"
                        >
                          <cv-overflow-menu
                            flip-menu
                            class="table-overflow-menu"
                          >
                            <cv-overflow-menu-item
                              @click="showEditAgentModal(agentData)"
                            >
                              <NsMenuItem
                                :icon="Edit20"
                                :label="$t('settings.edit_agent')"
                              />
                            </cv-overflow-menu-item>
                            <cv-overflow-menu-item
                              :disabled="agentData.status === 'start'"
                              @click="setAgentStatus(agentData.id, 'start')"
                            >
                              <NsMenuItem
                                :icon="Play20"
                                :label="$t('settings.start_agent')"
                              />
                            </cv-overflow-menu-item>
                            <cv-overflow-menu-item
                              :disabled="agentData.status === 'stop'"
                              @click="setAgentStatus(agentData.id, 'stop')"
                            >
                              <NsMenuItem
                                :icon="Stop20"
                                :label="$t('settings.stop_agent')"
                              />
                            </cv-overflow-menu-item>
                            <cv-overflow-menu-item
                              danger
                              @click="showDeleteAgentModal(agentData)"
                            >
                              <NsMenuItem
                                :icon="TrashCan20"
                                :label="$t('settings.delete_agent')"
                              />
                            </cv-overflow-menu-item>
                          </cv-overflow-menu>
                        </cv-structured-list-data>
                      </cv-structured-list-item>
                    </template>
                  </cv-structured-list>
                </cv-column>
              </cv-row>
              <cv-row v-if="showPageConfigureError">
                <cv-column>
                  <NsInlineNotification
                    kind="error"
                    :title="$t('action.configure-module')"
                    :description="error.configureModule"
                    :showCloseButton="false"
                  />
                </cv-column>
              </cv-row>
              <cv-row class="footer-actions-row">
                <cv-column class="footer-actions-column">
                  <NsButton
                    kind="primary"
                    :icon="Save20"
                    :loading="
                      loading.configureModule && configureMode === 'page'
                    "
                    :disabled="
                      loading.getConfiguration || loading.configureModule
                    "
                    @click="saveAgentsFromPage"
                  >
                    {{ $t("settings.save") }}
                  </NsButton>
                </cv-column>
              </cv-row>
            </cv-grid>
          </cv-tile>
        </cv-column>
      </cv-row>
    </cv-grid>

    <NsModal
      size="default"
      :visible="isShownCreateAgentModal"
      :primary-button-disabled="loading.configureModule"
      :isLoading="loading.configureModule && configureMode === 'create'"
      @modal-hidden="hideCreateAgentModal"
      @primary-click="createAgent"
    >
      <template slot="title">{{ $t("settings.create_agent_title") }}</template>
      <template slot="content">
        <cv-form @submit.prevent="createAgent">
          <NsTextInput
            v-model.trim="createAgentForm.name"
            :label="$t('settings.agent_name')"
            :placeholder="$t('settings.agent_name_placeholder')"
            :invalid-message="error.createAgentName"
            :disabled="loading.configureModule"
            data-modal-primary-focus
            ref="createAgentName"
          />
          <cv-select
            v-model="createAgentForm.role"
            :label="$t('settings.role')"
            :invalid-message="error.createAgentRole"
            :disabled="loading.configureModule"
            ref="createAgentRole"
            class="mg-bottom-lg"
          >
            <cv-select-option v-for="role in roles" :key="`create-${role}`" :value="role">
              {{ roleLabel(role) }}
            </cv-select-option>
          </cv-select>
          <div class="gateway-checkbox mg-bottom-lg">
            <label>
              <input
                v-model="createAgentForm.use_default_gateway_for_llm"
                type="checkbox"
                class="gateway-checkbox-input"
                :disabled="loading.configureModule"
              />
              {{ $t("settings.use_default_gateway_for_llm") }}
            </label>
            <p class="field-helper">
              {{ $t("settings.use_default_gateway_for_llm_help") }}
            </p>
          </div>
          <NsInlineNotification
            v-if="showCreateAgentError"
            kind="error"
            :title="$t('action.configure-module')"
            :description="error.configureModule"
            :showCloseButton="false"
          />
        </cv-form>
      </template>
      <template slot="secondary-button">{{
        core.$t("common.cancel")
      }}</template>
      <template slot="primary-button">{{
        $t("settings.create_agent")
      }}</template>
    </NsModal>

    <NsModal
      size="default"
      :visible="isShownEditAgentModal"
      :primary-button-disabled="loading.configureModule"
      :isLoading="loading.configureModule && configureMode === 'edit'"
      @modal-hidden="hideEditAgentModal"
      @primary-click="updateAgent"
    >
      <template slot="title">{{ $t("settings.edit_agent_title") }}</template>
      <template slot="content">
        <cv-form @submit.prevent="updateAgent">
          <NsTextInput
            v-model.trim="editAgentForm.name"
            :label="$t('settings.agent_name')"
            :placeholder="$t('settings.agent_name_placeholder')"
            :invalid-message="error.editAgentName"
            :disabled="loading.configureModule"
            data-modal-primary-focus
            ref="editAgentName"
          />
          <cv-select
            v-model="editAgentForm.role"
            :label="$t('settings.role')"
            :invalid-message="error.editAgentRole"
            :disabled="loading.configureModule"
            ref="editAgentRole"
            class="mg-bottom-lg"
          >
            <cv-select-option v-for="role in roles" :key="`edit-${role}`" :value="role">
              {{ roleLabel(role) }}
            </cv-select-option>
          </cv-select>
          <div class="gateway-checkbox mg-bottom-lg">
            <label>
              <input
                v-model="editAgentForm.use_default_gateway_for_llm"
                type="checkbox"
                class="gateway-checkbox-input"
                :disabled="loading.configureModule"
              />
              {{ $t("settings.use_default_gateway_for_llm") }}
            </label>
            <p class="field-helper">
              {{ $t("settings.use_default_gateway_for_llm_help") }}
            </p>
          </div>
          <NsInlineNotification
            v-if="showEditAgentError"
            kind="error"
            :title="$t('action.configure-module')"
            :description="error.configureModule"
            :showCloseButton="false"
          />
        </cv-form>
      </template>
      <template slot="secondary-button">{{
        core.$t("common.cancel")
      }}</template>
      <template slot="primary-button">{{
        $t("settings.save")
      }}</template>
    </NsModal>

    <NsModal
      size="default"
      kind="danger"
      :visible="isShownDeleteAgentModal"
      :primary-button-disabled="loading.configureModule"
      :isLoading="loading.configureModule && configureMode === 'delete'"
      @modal-hidden="hideDeleteAgentModal"
      @primary-click="deleteAgent"
    >
      <template slot="title">
        {{
          $t("settings.delete_agent_title", {
            name: agentToDelete ? agentToDelete.name : "",
          })
        }}
      </template>
      <template slot="content">
        <p>
          {{
            $t("settings.delete_agent_description", {
              name: agentToDelete ? agentToDelete.name : "",
            })
          }}
        </p>
        <NsInlineNotification
          v-if="showDeleteAgentError"
          kind="error"
          :title="$t('action.configure-module')"
          :description="error.configureModule"
          :showCloseButton="false"
        />
      </template>
      <template slot="secondary-button">{{
        core.$t("common.cancel")
      }}</template>
      <template slot="primary-button">{{
        $t("settings.delete_agent")
      }}</template>
    </NsModal>
  </div>
</template>

<script>
import to from "await-to-js";
import { mapState } from "vuex";
import {
  QueryParamService,
  UtilService,
  TaskService,
  IconService,
  PageTitleService,
} from "@nethserver/ns8-ui-lib";

export default {
  name: "Settings",
  mixins: [
    TaskService,
    IconService,
    UtilService,
    QueryParamService,
    PageTitleService,
  ],
  pageTitle() {
    return this.$t("settings.title") + " - " + this.appName;
  },
  data() {
    return {
      q: {
        page: "settings",
      },
      urlCheckInterval: null,
      roles: [
        "default",
        "developer",
        "marketing",
        "sales",
        "customer_support",
        "social_media_manager",
        "business_consultant",
        "researcher",
      ],
      openviking: this.defaultOpenVikingState(),
      loadedOpenViking: this.defaultOpenVikingState(),
      agents: [],
      submittedAgents: [],
      configureMode: "",
      isShownCreateAgentModal: false,
      isShownEditAgentModal: false,
      isShownDeleteAgentModal: false,
      agentToEdit: null,
      agentToDelete: null,
      createAgentForm: {
        name: "",
        role: "default",
        use_default_gateway_for_llm: false,
      },
      editAgentForm: {
        name: "",
        role: "default",
        use_default_gateway_for_llm: false,
      },
      loading: {
        getConfiguration: false,
        configureModule: false,
      },
      error: {
        getConfiguration: "",
        configureModule: "",
        createAgentName: "",
        createAgentRole: "",
        editAgentName: "",
        editAgentRole: "",
        embeddingProvider: "",
        embeddingApiKey: "",
      },
    };
  },
  computed: {
    ...mapState(["instanceName", "core", "appName"]),
    embeddingProviders() {
      return [
        { value: "openai", label: this.$t("settings.embedding_provider_openai") },
        { value: "volcengine", label: this.$t("settings.embedding_provider_volcengine") },
        { value: "jina", label: this.$t("settings.embedding_provider_jina") },
        { value: "voyage", label: this.$t("settings.embedding_provider_voyage") },
        { value: "minimax", label: this.$t("settings.embedding_provider_minimax") },
        { value: "gemini", label: this.$t("settings.embedding_provider_gemini") },
      ];
    },
    visibleAgents() {
      return this.agents.filter((agentData) => !agentData.hidden);
    },
    embeddingApiKeyHelper() {
      if (this.openviking.embedding.api_key_configured && !this.openviking.embedding.api_key) {
        return this.$t("settings.embedding_api_key_preserved");
      }

      return this.$t("settings.embedding_api_key_help");
    },
    showEmbeddingChangeWarning() {
      const initialProvider = this.loadedOpenViking.embedding.provider;
      const currentProvider = this.openviking.embedding.provider;

      return !!initialProvider && initialProvider !== currentProvider;
    },
    showPageConfigureError() {
      return this.configureMode === "page" && !!this.error.configureModule;
    },
    showCreateAgentError() {
      return this.configureMode === "create" && !!this.error.configureModule;
    },
    showEditAgentError() {
      return this.configureMode === "edit" && !!this.error.configureModule;
    },
    showDeleteAgentError() {
      return this.configureMode === "delete" && !!this.error.configureModule;
    },
  },
  beforeRouteEnter(to, from, next) {
    next((vm) => {
      vm.watchQueryData(vm);
      vm.urlCheckInterval = vm.initUrlBindingForApp(vm, vm.q.page);
    });
  },
  beforeRouteLeave(to, from, next) {
    clearInterval(this.urlCheckInterval);
    next();
  },
  created() {
    this.getConfiguration();
  },
  methods: {
    async getConfiguration() {
      this.loading.getConfiguration = true;
      this.error.getConfiguration = "";
      const taskAction = "get-configuration";
      const eventId = this.getUuid();

      // register to task error
      this.core.$root.$once(
        `${taskAction}-aborted-${eventId}`,
        this.getConfigurationAborted
      );

      // register to task completion
      this.core.$root.$once(
        `${taskAction}-completed-${eventId}`,
        this.getConfigurationCompleted
      );

      const res = await to(
        this.createModuleTaskForApp(this.instanceName, {
          action: taskAction,
          extra: {
            title: this.$t("action." + taskAction),
            isNotificationHidden: true,
            eventId,
          },
        })
      );
      const err = res[0];

      if (err) {
        console.error(`error creating task ${taskAction}`, err);
        this.error.getConfiguration = this.getErrorMessage(err);
        this.loading.getConfiguration = false;
        return;
      }
    },
    getConfigurationAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.error.getConfiguration = this.$t("error.generic_error");
      this.loading.getConfiguration = false;
    },
    getConfigurationCompleted(taskContext, taskResult) {
      this.loading.getConfiguration = false;
      const config = taskResult.output;

      this.agents = this.normalizeAgents(config.agents || []);
      this.openviking = this.normalizeOpenViking(config.openviking || {});
      this.loadedOpenViking = this.normalizeOpenViking(config.openviking || {});
    },
    configureModuleValidationFailed(validationErrors) {
      this.loading.configureModule = false;
      let focusAlreadySet = false;

      if (this.configureMode === "create") {
        this.clearCreateAgentErrors();
      }
      if (this.configureMode === "edit") {
        this.clearEditAgentErrors();
      }
      this.clearOpenVikingErrors();

      for (const validationError of validationErrors) {
        const field = validationError.field || validationError.parameter || "";

        if (["create", "edit"].includes(this.configureMode) && field !== "(root)" && field !== "") {
          const nameErrorField = this.configureMode === "create" ? "createAgentName" : "editAgentName";
          const roleErrorField = this.configureMode === "create" ? "createAgentRole" : "editAgentRole";

          if (field.endsWith("name")) {
            this.error[nameErrorField] = this.$t("settings.agent_name_invalid");

            if (!focusAlreadySet) {
              this.focusElement(nameErrorField);
              focusAlreadySet = true;
            }
          }

          if (field.endsWith("role")) {
            this.error[roleErrorField] = this.$t("settings.agent_role_invalid");

            if (!focusAlreadySet) {
              this.focusElement(roleErrorField);
              focusAlreadySet = true;
            }
          }
        }

        if (field.includes("provider")) {
          this.error.embeddingProvider = this.$t(
            "settings.embedding_provider_invalid"
          );

          if (!focusAlreadySet) {
            this.focusElement("embeddingProvider");
            focusAlreadySet = true;
          }
        }

        if (field.includes("api_key")) {
          this.error.embeddingApiKey = this.$t(
            "settings.embedding_api_key_invalid"
          );

          if (!focusAlreadySet) {
            this.focusElement("embeddingApiKey");
            focusAlreadySet = true;
          }
        }
      }

      this.error.configureModule = this.$t("error.validation_error");
    },
    async saveAgents(nextAgents, mode) {
      this.loading.configureModule = true;
      this.error.configureModule = "";
      this.clearOpenVikingErrors();
      this.configureMode = mode;
      this.submittedAgents = this.normalizeAgents(nextAgents);
      const taskAction = "configure-module";
      const eventId = this.getUuid();

      this.core.$root.$once(
        `${taskAction}-aborted-${eventId}`,
        this.configureModuleAborted
      );

      this.core.$root.$once(
        `${taskAction}-validation-failed-${eventId}`,
        this.configureModuleValidationFailed
      );

      this.core.$root.$once(
        `${taskAction}-completed-${eventId}`,
        this.configureModuleCompleted
      );

      const res = await to(
        this.createModuleTaskForApp(this.instanceName, {
          action: taskAction,
          data: {
            agents: this.buildAgentPayload(this.submittedAgents),
            openviking: this.buildOpenVikingPayload(),
          },
          extra: {
            title: this.$t("settings.configure_instance", {
              instance: this.instanceName,
            }),
            description: this.$t("common.processing"),
            eventId,
          },
        })
      );
      const err = res[0];

      if (err) {
        console.error(`error creating task ${taskAction}`, err);
        this.error.configureModule = this.getErrorMessage(err);
        this.loading.configureModule = false;
      }
    },
    normalizeAgents(agents) {
      return agents
        .map((agentData) => {
          const normalizedAgent = {
            id: Number(agentData.id),
            name: (agentData.name || "").trim(),
            role: agentData.role,
            status: agentData.status === "stop" ? "stop" : "start",
            use_default_gateway_for_llm: !!agentData.use_default_gateway_for_llm,
            hidden: !!agentData.hidden,
            protected: !!agentData.protected,
            system: !!agentData.system,
          };

          for (const field of ["account", "user", "agent_id"]) {
            if (typeof agentData[field] === "string") {
              const normalizedValue = agentData[field].trim();
              if (normalizedValue) {
                normalizedAgent[field] = normalizedValue;
              }
            }
          }

          return normalizedAgent;
        })
        .filter((agentData) => {
          return (
            Number.isInteger(agentData.id) &&
            agentData.id >= 0 &&
            agentData.name &&
            this.roles.includes(agentData.role)
          );
        })
        .sort((left, right) => left.id - right.id);
    },
    defaultOpenVikingState() {
      return {
        embedding: {
          provider: "",
          api_key: "",
          api_key_configured: false,
        },
      };
    },
    normalizeOpenViking(openvikingData) {
      const normalized = this.defaultOpenVikingState();
      const embedding = openvikingData.embedding || {};

      if (typeof embedding.provider === "string") {
        normalized.embedding.provider = embedding.provider.trim();
      }
      normalized.embedding.api_key_configured = !!embedding.api_key_configured;

      return normalized;
    },
    clearOpenVikingErrors() {
      this.error.embeddingProvider = "";
      this.error.embeddingApiKey = "";
    },
    validateOpenViking() {
      this.clearOpenVikingErrors();

      const provider = this.openviking.embedding.provider;
      const apiKey = this.openviking.embedding.api_key;
      const providerChanged =
        this.loadedOpenViking.embedding.provider !== provider;

      if (apiKey && !provider) {
        this.error.embeddingProvider = this.$t("common.required");
        this.focusElement("embeddingProvider");
        return false;
      }

      if (!provider) {
        return true;
      }

      if (
        !apiKey &&
        (!this.openviking.embedding.api_key_configured || providerChanged)
      ) {
        this.error.embeddingApiKey = this.$t("common.required");
        this.focusElement("embeddingApiKey");
        return false;
      }

      return true;
    },
    buildOpenVikingPayload() {
      const embeddingPayload = {};
      if (this.openviking.embedding.provider) {
        embeddingPayload.provider = this.openviking.embedding.provider;
      }
      if (this.openviking.embedding.api_key) {
        embeddingPayload.api_key = this.openviking.embedding.api_key;
      }

      return {
        embedding: embeddingPayload,
      };
    },
    buildAgentPayload(agents) {
      return agents.map((agentData) => {
        const payload = {
          id: agentData.id,
          name: agentData.name,
          role: agentData.role,
          status: agentData.status,
          use_default_gateway_for_llm: !!agentData.use_default_gateway_for_llm,
        };

        for (const field of ["account", "user", "agent_id"]) {
          if (typeof agentData[field] === "string" && agentData[field]) {
            payload[field] = agentData[field];
          }
        }

        return payload;
      });
    },
    nextAgentId() {
      return (
        this.visibleAgents.reduce((maxId, agentData) => {
          return Math.max(maxId, agentData.id);
        }, 0) + 1
      );
    },
    roleLabel(role) {
      return this.$t(`settings.role_${role}`);
    },
    statusKind(status) {
      return status === "stop" ? "high-contrast" : "green";
    },
    statusLabel(status) {
      return this.$t(`settings.status_${status}`);
    },
    clearCreateAgentErrors() {
      this.error.createAgentName = "";
      this.error.createAgentRole = "";
    },
    clearEditAgentErrors() {
      this.error.editAgentName = "";
      this.error.editAgentRole = "";
    },
    resetCreateAgentForm() {
      this.createAgentForm = {
        name: "",
        role: "default",
        use_default_gateway_for_llm: false,
      };
      this.clearCreateAgentErrors();
    },
    resetEditAgentForm() {
      this.editAgentForm = {
        name: "",
        role: "default",
        use_default_gateway_for_llm: false,
      };
      this.clearEditAgentErrors();
    },
    showCreateAgentModal() {
      this.resetCreateAgentForm();
      this.error.configureModule = "";
      this.configureMode = "";
      this.isShownCreateAgentModal = true;

      this.$nextTick(() => {
        this.focusElement("createAgentName");
      });
    },
    hideCreateAgentModal() {
      if (this.loading.configureModule && this.configureMode === "create") {
        return;
      }

      this.isShownCreateAgentModal = false;
      this.resetCreateAgentForm();

      if (this.configureMode === "create") {
        this.configureMode = "";
        this.error.configureModule = "";
      }
    },
    showEditAgentModal(agentData) {
      this.agentToEdit = agentData;
      this.editAgentForm = {
        name: agentData.name,
        role: agentData.role,
        use_default_gateway_for_llm: !!agentData.use_default_gateway_for_llm,
      };
      this.clearEditAgentErrors();
      this.error.configureModule = "";
      this.configureMode = "";
      this.isShownEditAgentModal = true;

      this.$nextTick(() => {
        this.focusElement("editAgentName");
      });
    },
    hideEditAgentModal() {
      if (this.loading.configureModule && this.configureMode === "edit") {
        return;
      }

      this.isShownEditAgentModal = false;
      this.agentToEdit = null;
      this.resetEditAgentForm();

      if (this.configureMode === "edit") {
        this.configureMode = "";
        this.error.configureModule = "";
      }
    },
    validateCreateAgent() {
      this.clearCreateAgentErrors();
      this.error.configureModule = "";

      let isValidationOk = true;
      const trimmedName = this.createAgentForm.name.trim();

      if (!trimmedName) {
        this.error.createAgentName = this.$t("common.required");
        this.focusElement("createAgentName");
        isValidationOk = false;
      } else if (!/^[A-Za-z ]+$/.test(trimmedName)) {
        this.error.createAgentName = this.$t("settings.agent_name_invalid");
        this.focusElement("createAgentName");
        isValidationOk = false;
      }

      if (!this.roles.includes(this.createAgentForm.role)) {
        this.error.createAgentRole = this.$t("settings.agent_role_invalid");

        if (isValidationOk) {
          this.focusElement("createAgentRole");
          isValidationOk = false;
        }
      }

      return isValidationOk;
    },
    validateEditAgent() {
      this.clearEditAgentErrors();
      this.error.configureModule = "";

      let isValidationOk = true;
      const trimmedName = this.editAgentForm.name.trim();

      if (!trimmedName) {
        this.error.editAgentName = this.$t("common.required");
        this.focusElement("editAgentName");
        isValidationOk = false;
      } else if (!/^[A-Za-z ]+$/.test(trimmedName)) {
        this.error.editAgentName = this.$t("settings.agent_name_invalid");
        this.focusElement("editAgentName");
        isValidationOk = false;
      }

      if (!this.roles.includes(this.editAgentForm.role)) {
        this.error.editAgentRole = this.$t("settings.agent_role_invalid");

        if (isValidationOk) {
          this.focusElement("editAgentRole");
          isValidationOk = false;
        }
      }

      return isValidationOk;
    },
    createAgent() {
      if (!this.validateCreateAgent()) {
        return;
      }

      const nextAgents = [
        ...this.visibleAgents,
        {
          id: this.nextAgentId(),
          name: this.createAgentForm.name.trim(),
          role: this.createAgentForm.role,
          status: "start",
          use_default_gateway_for_llm: this.createAgentForm.use_default_gateway_for_llm,
        },
      ];

      this.saveAgents(nextAgents, "create");
    },
    updateAgent() {
      if (!this.agentToEdit || !this.validateEditAgent()) {
        return;
      }

      const nextAgents = this.visibleAgents.map((agentData) => {
        if (agentData.id !== this.agentToEdit.id) {
          return agentData;
        }

        return {
          ...agentData,
          name: this.editAgentForm.name.trim(),
          role: this.editAgentForm.role,
          use_default_gateway_for_llm: this.editAgentForm.use_default_gateway_for_llm,
        };
      });

      this.saveAgents(nextAgents, "edit");
    },
    showDeleteAgentModal(agentData) {
      this.agentToDelete = agentData;
      this.error.configureModule = "";
      this.configureMode = "";
      this.isShownDeleteAgentModal = true;
    },
    hideDeleteAgentModal() {
      if (this.loading.configureModule && this.configureMode === "delete") {
        return;
      }

      this.isShownDeleteAgentModal = false;
      this.agentToDelete = null;

      if (this.configureMode === "delete") {
        this.configureMode = "";
        this.error.configureModule = "";
      }
    },
    deleteAgent() {
      if (!this.agentToDelete) {
        return;
      }

      const nextAgents = this.visibleAgents.filter((agentData) => {
        return agentData.id !== this.agentToDelete.id;
      });

      this.saveAgents(nextAgents, "delete");
    },
    setAgentStatus(agentId, status) {
      this.error.configureModule = "";
      this.agents = this.agents.map((agentData) => {
        if (agentData.id !== agentId) {
          return agentData;
        }

        return {
          ...agentData,
          status,
        };
      });
    },
    saveAgentsFromPage() {
      if (!this.validateOpenViking()) {
        return;
      }

      this.saveAgents(this.visibleAgents, "page");
    },
    configureModuleAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.error.configureModule = this.$t("error.generic_error");
      this.loading.configureModule = false;
    },
    configureModuleCompleted() {
      const mode = this.configureMode;

      this.loading.configureModule = false;
      this.error.configureModule = "";

      if (mode === "create") {
        this.isShownCreateAgentModal = false;
        this.resetCreateAgentForm();
        this.getConfiguration();
        return;
      }

      if (mode === "edit") {
        this.isShownEditAgentModal = false;
        this.agentToEdit = null;
        this.resetEditAgentForm();
        this.getConfiguration();
        return;
      }

      if (mode === "delete") {
        this.isShownDeleteAgentModal = false;
        this.agentToDelete = null;
        this.getConfiguration();
        return;
      }

      this.getConfiguration();
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";

.toolbar-row {
  margin-bottom: $spacing-06;
}

.section-tile {
  margin-bottom: $spacing-06;
}

.toolbar-actions {
  display: flex;
  justify-content: flex-end;
}

.section-title {
  margin-bottom: $spacing-03;
}

.section-description {
  margin: 0;
  color: $text-secondary;
  max-width: 36rem;
}

.table-overflow-menu-cell {
  width: 1%;
}

.footer-actions-row {
  margin-top: $spacing-07;
}

.footer-actions-column {
  display: flex;
  justify-content: flex-end;
}

.break-word {
  word-break: break-word;
}

.field-helper {
  margin-top: $spacing-03;
  color: $text-secondary;
}

.gateway-flag {
  margin: $spacing-02 0 0;
  color: $text-secondary;
  font-size: 0.875rem;
}

.gateway-checkbox {
  display: flex;
  flex-direction: column;
}

.gateway-checkbox-input {
  margin-right: $spacing-03;
}

@media (max-width: 671px) {
  .toolbar-actions {
    justify-content: flex-start;
    margin-top: $spacing-05;
  }
}
</style>
