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
                  <p v-if="isAgentLimitReached" class="section-description">
                    {{ $t("settings.agent_limit_reached") }}
                  </p>
                </cv-column>
                <cv-column :md="2" :max="8" class="toolbar-actions">
                  <NsButton
                    kind="secondary"
                    :icon="Add20"
                    :disabled="
                      loading.getConfiguration ||
                      loading.configureModule ||
                      isAgentLimitReached
                    "
                    @click="showCreateAgentModal"
                  >
                    {{ $t("settings.create_agent") }}
                  </NsButton>
                </cv-column>
              </cv-row>
              <cv-row>
                <cv-column :md="6" :max="8">
                  <NsTextInput
                    v-model.trim="baseVirtualhost"
                    :label="$t('settings.base_virtualhost')"
                    :placeholder="$t('settings.base_virtualhost_placeholder')"
                    :invalid-message="error.baseVirtualhost"
                    :disabled="
                      loading.getConfiguration || loading.configureModule
                    "
                    ref="baseVirtualhost"
                  />
                  <p class="section-description">
                    {{ $t("settings.base_virtualhost_description") }}
                  </p>
                  <cv-select
                    v-model="userDomain"
                    :label="$t('settings.user_domain')"
                    :invalid-message="error.userDomain"
                    :disabled="
                      loading.getConfiguration ||
                      loading.configureModule ||
                      loading.listUserDomains
                    "
                    ref="userDomain"
                    class="mg-bottom-lg"
                    @change="onUserDomainChanged"
                  >
                    <cv-select-option value="">
                      {{ $t("settings.user_domain_placeholder") }}
                    </cv-select-option>
                    <cv-select-option
                      v-for="domain in userDomains"
                      :key="domain.name"
                      :value="domain.name"
                    >
                      {{ domainLabel(domain) }}
                    </cv-select-option>
                  </cv-select>
                  <p class="section-description">
                    {{ $t("settings.user_domain_description") }}
                  </p>
                  <NsInlineNotification
                    v-if="error.listUserDomains"
                    kind="warning"
                    :title="$t('action.list-user-domains')"
                    :description="error.listUserDomains"
                    :showCloseButton="false"
                  />
                  <NsToggle
                    value="letsEncrypt"
                    :label="$t('settings.request_le_certificates')"
                    v-model="letsEncrypt"
                    :disabled="
                      loading.getConfiguration || loading.configureModule
                    "
                  >
                    <template #tooltip>
                      <div class="mg-bottom-sm">
                        {{ $t("settings.request_le_certificates_tooltip") }}
                      </div>
                      <div class="mg-bottom-sm">
                        <cv-link @click="goToCertificates">
                          {{
                            core.$t("apps_lets_encrypt.go_to_tls_certificates")
                          }}
                        </cv-link>
                      </div>
                    </template>
                    <template slot="text-left">{{
                      core.$t("common.disabled")
                    }}</template>
                    <template slot="text-right">{{
                      core.$t("common.enabled")
                    }}</template>
                  </NsToggle>
                  <NsInlineNotification
                    v-if="isLetsEncryptCurrentlyEnabled && !letsEncrypt"
                    kind="warning"
                    :title="
                      core.$t('apps_lets_encrypt.lets_encrypt_disabled_warning')
                    "
                    :description="
                      $t(
                        'settings.request_le_certificates_disabled_warning_description'
                      )
                    "
                    :showCloseButton="false"
                  />
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
                    v-else-if="!agents.length"
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
                        {{ $t("settings.allowed_user") }}
                      </cv-structured-list-heading>
                      <cv-structured-list-heading>
                        {{ $t("settings.dashboard") }}
                      </cv-structured-list-heading>
                      <cv-structured-list-heading>
                        {{ $t("settings.actions") }}
                      </cv-structured-list-heading>
                    </template>
                    <template slot="items">
                      <cv-structured-list-item
                        v-for="agentData in agents"
                        :key="agentData.id"
                      >
                        <cv-structured-list-data class="break-word">
                          {{ agentData.name }}
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
                        <cv-structured-list-data class="break-word">
                          {{ agentData.allowed_user || $t("settings.allowed_user_not_set") }}
                        </cv-structured-list-data>
                        <cv-structured-list-data class="break-word">
                          <cv-link
                            v-if="agentDashboardUrl(agentData)"
                            :href="agentDashboardUrl(agentData)"
                            target="_blank"
                          >
                            {{ agentDashboardUrl(agentData) }}
                          </cv-link>
                          <span v-else>{{
                            $t("settings.dashboard_not_configured")
                          }}</span>
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
            <cv-select-option
              v-for="role in roles"
              :key="`create-${role}`"
              :value="role"
            >
              {{ roleLabel(role) }}
            </cv-select-option>
          </cv-select>
          <cv-select
            v-model="createAgentForm.allowed_user"
            :label="$t('settings.allowed_user')"
            :invalid-message="error.createAgentAllowedUser"
            :disabled="
              loading.configureModule ||
              loading.listDomainUsers ||
              !normalizeUserDomain() ||
              !normalizedBaseVirtualhost
            "
            ref="createAgentAllowedUser"
            class="mg-bottom-lg"
          >
            <cv-select-option value="">
              {{ allowedUserPlaceholder }}
            </cv-select-option>
            <cv-select-option
              v-for="userRecord in domainUsers"
              :key="`create-${userRecord.user}`"
              :value="userRecord.user"
            >
              {{ domainUserLabel(userRecord) }}
            </cv-select-option>
          </cv-select>
          <p class="section-description mg-bottom-lg">
            {{ $t("settings.allowed_user_description") }}
          </p>
          <NsInlineNotification
            v-if="error.listDomainUsers && normalizeUserDomain()"
            kind="warning"
            :title="$t('action.list-domain-users')"
            :description="error.listDomainUsers"
            :showCloseButton="false"
          />
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
            <cv-select-option
              v-for="role in roles"
              :key="`edit-${role}`"
              :value="role"
            >
              {{ roleLabel(role) }}
            </cv-select-option>
          </cv-select>
          <cv-select
            v-model="editAgentForm.allowed_user"
            :label="$t('settings.allowed_user')"
            :invalid-message="error.editAgentAllowedUser"
            :disabled="
              loading.configureModule ||
              loading.listDomainUsers ||
              !normalizeUserDomain() ||
              !normalizedBaseVirtualhost
            "
            ref="editAgentAllowedUser"
            class="mg-bottom-lg"
          >
            <cv-select-option value="">
              {{ allowedUserPlaceholder }}
            </cv-select-option>
            <cv-select-option
              v-for="userRecord in domainUsers"
              :key="`edit-${userRecord.user}`"
              :value="userRecord.user"
            >
              {{ domainUserLabel(userRecord) }}
            </cv-select-option>
          </cv-select>
          <p class="section-description mg-bottom-lg">
            {{ $t("settings.allowed_user_description") }}
          </p>
          <NsInlineNotification
            v-if="error.listDomainUsers && normalizeUserDomain()"
            kind="warning"
            :title="$t('action.list-domain-users')"
            :description="error.listDomainUsers"
            :showCloseButton="false"
          />
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
      <template slot="primary-button">{{ $t("settings.save") }}</template>
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
      baseVirtualhost: "",
      userDomain: "",
      letsEncrypt: false,
      isLetsEncryptCurrentlyEnabled: false,
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
      userDomains: [],
      domainUsers: [],
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
        allowed_user: "",
      },
      editAgentForm: {
        name: "",
        role: "default",
        allowed_user: "",
      },
      loading: {
        getConfiguration: false,
        configureModule: false,
        listUserDomains: false,
        listDomainUsers: false,
      },
      error: {
        getConfiguration: "",
        configureModule: "",
        baseVirtualhost: "",
        userDomain: "",
        listUserDomains: "",
        listDomainUsers: "",
        createAgentName: "",
        createAgentRole: "",
        createAgentAllowedUser: "",
        editAgentName: "",
        editAgentRole: "",
        editAgentAllowedUser: "",
      },
    };
  },
  computed: {
    ...mapState(["instanceName", "core", "appName"]),
    normalizedBaseVirtualhost() {
      return this.normalizeBaseVirtualhost();
    },
    allowedUserPlaceholder() {
      if (!this.normalizedBaseVirtualhost) {
        return this.$t("settings.allowed_user_not_required");
      }

      if (!this.normalizeUserDomain()) {
        return this.$t("settings.allowed_user_select_domain_first");
      }

      if (this.loading.listDomainUsers) {
        return this.$t("common.processing");
      }

      return this.$t("settings.allowed_user_placeholder");
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
    isAgentLimitReached() {
      return this.agents.length >= 30;
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
        this.error.getConfiguration = this.getErrorMessage(err);
        this.loading.getConfiguration = false;
        return;
      }
    },
    getConfigurationAborted() {
      this.error.getConfiguration = this.$t("error.generic_error");
      this.loading.getConfiguration = false;
    },
    getConfigurationCompleted(taskContext, taskResult) {
      this.loading.getConfiguration = false;
      const config = taskResult.output;

      this.baseVirtualhost = this.normalizeBaseVirtualhost(
        config.base_virtualhost || ""
      );
      this.userDomain = this.normalizeUserDomain(config.user_domain || "");
      this.letsEncrypt = !!config.lets_encrypt;
      this.isLetsEncryptCurrentlyEnabled = !!config.lets_encrypt;
      this.agents = this.normalizeAgents(config.agents || []);
      this.loadUserDomains();
      this.loadDomainUsers(this.userDomain);
    },
    configureModuleValidationFailed(validationErrors) {
      this.loading.configureModule = false;
      let focusAlreadySet = false;

      this.error.baseVirtualhost = "";
      this.error.userDomain = "";

      if (this.configureMode === "create") {
        this.clearCreateAgentErrors();
      }
      if (this.configureMode === "edit") {
        this.clearEditAgentErrors();
      }

      for (const validationError of validationErrors) {
        const field = validationError.field || validationError.parameter || "";

        if (
          ["create", "edit"].includes(this.configureMode) &&
          field !== "(root)" &&
          field !== ""
        ) {
          const nameErrorField =
            this.configureMode === "create"
              ? "createAgentName"
              : "editAgentName";
          const roleErrorField =
            this.configureMode === "create"
              ? "createAgentRole"
              : "editAgentRole";
          const allowedUserErrorField =
            this.configureMode === "create"
              ? "createAgentAllowedUser"
              : "editAgentAllowedUser";

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

          if (field.endsWith("allowed_user")) {
            this.error[allowedUserErrorField] = this.$t(
              validationError.error === "agent_allowed_user_required"
                ? "settings.allowed_user_required"
                : "settings.allowed_user_invalid"
            );

            if (!focusAlreadySet) {
              this.focusElement(allowedUserErrorField);
              focusAlreadySet = true;
            }
          }
        }

        if (field.endsWith("base_virtualhost")) {
          this.error.baseVirtualhost = this.$t(
            "settings.base_virtualhost_invalid"
          );

          if (!focusAlreadySet) {
            this.focusElement("baseVirtualhost");
            focusAlreadySet = true;
          }
        }

        if (field === "user_domain") {
          this.error.userDomain = this.$t(
            validationError.error === "user_domain_required"
              ? "settings.user_domain_required"
              : "settings.user_domain_invalid"
          );

          if (!focusAlreadySet) {
            this.focusElement("userDomain");
            focusAlreadySet = true;
          }
        }
      }

      this.error.configureModule = this.$t("error.validation_error");
    },
    async saveAgents(nextAgents, mode) {
      this.error.baseVirtualhost = "";
      this.error.userDomain = "";
      if (!this.validateBaseVirtualhost()) {
        this.error.configureModule = this.$t("error.validation_error");
        return;
      }
      if (!this.validateUserDomain(nextAgents)) {
        this.error.configureModule = this.$t("error.validation_error");
        return;
      }

      this.loading.configureModule = true;
      this.error.configureModule = "";
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
            base_virtualhost: this.normalizeBaseVirtualhost(),
            user_domain: this.normalizeUserDomain(),
            lets_encrypt: this.letsEncrypt,
            agents: this.buildAgentPayload(this.submittedAgents),
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
            allowed_user: this.normalizeAllowedUser(agentData.allowed_user),
          };

          return normalizedAgent;
        })
        .filter((agentData) => {
          return (
            Number.isInteger(agentData.id) &&
            agentData.id >= 1 &&
            agentData.name &&
            this.roles.includes(agentData.role)
          );
        })
        .sort((left, right) => left.id - right.id);
    },
    buildAgentPayload(agents) {
      return agents.map((agentData) => {
        return {
          id: agentData.id,
          name: agentData.name,
          role: agentData.role,
          status: agentData.status,
          allowed_user: this.normalizeAllowedUser(agentData.allowed_user),
        };
      });
    },
    nextAgentId() {
      for (let candidateId = 1; candidateId <= 30; candidateId++) {
        if (!this.agents.some((agentData) => agentData.id === candidateId)) {
          return candidateId;
        }
      }

      return null;
    },
    normalizeBaseVirtualhost(value = this.baseVirtualhost) {
      return (value || "").trim().toLowerCase();
    },
    normalizeUserDomain(value = this.userDomain) {
      return (value || "").trim().toLowerCase();
    },
    normalizeAllowedUser(value) {
      return (value || "").trim();
    },
    normalizeUserDomains(domains) {
      return domains
        .map((domainData) => {
          return {
            name: this.normalizeUserDomain(domainData.name),
            schema: (domainData.schema || "").trim(),
            location: (domainData.location || "").trim(),
          };
        })
        .filter((domainData) => !!domainData.name)
        .sort((left, right) => left.name.localeCompare(right.name));
    },
    normalizeDomainUsers(users) {
      return users
        .map((userData) => {
          const displayName = Array.isArray(userData.display_name)
            ? userData.display_name.find((value) => !!value)
            : userData.display_name;

          return {
            user: this.normalizeAllowedUser(userData.user),
            display_name: (displayName || "").trim(),
            locked: userData.locked === true,
          };
        })
        .filter((userData) => !!userData.user)
        .sort((left, right) => left.user.localeCompare(right.user));
    },
    domainLabel(domainData) {
      const details = [domainData.schema, domainData.location].filter(Boolean);
      if (!details.length) {
        return domainData.name;
      }

      return `${domainData.name} (${details.join(", ")})`;
    },
    domainUserLabel(userData) {
      const label = userData.display_name && userData.display_name !== userData.user
        ? `${userData.display_name} (${userData.user})`
        : userData.user;

      if (!userData.locked) {
        return label;
      }

      return `${label} ${this.$t("settings.allowed_user_locked_suffix")}`;
    },
    validateBaseVirtualhost() {
      const normalizedBaseVirtualhost = this.normalizeBaseVirtualhost();
      if (
        normalizedBaseVirtualhost &&
        !/^(?=.{1,253}$)(?:(?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)+(?!-)[A-Za-z0-9-]{1,63}(?<!-)$/.test(
          normalizedBaseVirtualhost
        )
      ) {
        this.error.baseVirtualhost = this.$t(
          "settings.base_virtualhost_invalid"
        );
        return false;
      }

      return true;
    },
    validateUserDomain(nextAgents) {
      if (!this.normalizeBaseVirtualhost() || !nextAgents.length) {
        return true;
      }

      if (!this.normalizeUserDomain()) {
        this.error.userDomain = this.$t("settings.user_domain_required");
        this.focusElement("userDomain");
        return false;
      }

      return true;
    },
    agentDashboardUrl(agentData) {
      const normalizedBaseVirtualhost = this.normalizeBaseVirtualhost();
      if (!normalizedBaseVirtualhost) {
        return "";
      }

      return `https://${normalizedBaseVirtualhost}/hermes-${agentData.id}/`;
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
      this.error.createAgentAllowedUser = "";
    },
    clearEditAgentErrors() {
      this.error.editAgentName = "";
      this.error.editAgentRole = "";
      this.error.editAgentAllowedUser = "";
    },
    resetCreateAgentForm() {
      this.createAgentForm = {
        name: "",
        role: "default",
        allowed_user: "",
      };
      this.clearCreateAgentErrors();
    },
    resetEditAgentForm() {
      this.editAgentForm = {
        name: "",
        role: "default",
        allowed_user: "",
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
        allowed_user: this.normalizeAllowedUser(agentData.allowed_user),
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

      if (this.normalizeBaseVirtualhost()) {
        if (!this.normalizeUserDomain()) {
          this.error.userDomain = this.$t("settings.user_domain_required");

          if (isValidationOk) {
            this.focusElement("userDomain");
            isValidationOk = false;
          }
        } else if (!this.normalizeAllowedUser(this.createAgentForm.allowed_user)) {
          this.error.createAgentAllowedUser = this.$t(
            "settings.allowed_user_required"
          );

          if (isValidationOk) {
            this.focusElement("createAgentAllowedUser");
            isValidationOk = false;
          }
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

      if (this.normalizeBaseVirtualhost()) {
        if (!this.normalizeUserDomain()) {
          this.error.userDomain = this.$t("settings.user_domain_required");

          if (isValidationOk) {
            this.focusElement("userDomain");
            isValidationOk = false;
          }
        } else if (!this.normalizeAllowedUser(this.editAgentForm.allowed_user)) {
          this.error.editAgentAllowedUser = this.$t(
            "settings.allowed_user_required"
          );

          if (isValidationOk) {
            this.focusElement("editAgentAllowedUser");
            isValidationOk = false;
          }
        }
      }

      return isValidationOk;
    },
    createAgent() {
      if (!this.validateCreateAgent()) {
        return;
      }

      const nextId = this.nextAgentId();
      if (!nextId) {
        this.error.configureModule = this.$t("settings.agent_limit_reached");
        return;
      }

      const nextAgents = [
        ...this.agents,
        {
          id: nextId,
          name: this.createAgentForm.name.trim(),
          role: this.createAgentForm.role,
          status: "start",
          allowed_user: this.normalizeAllowedUser(
            this.createAgentForm.allowed_user
          ),
        },
      ];

      this.saveAgents(nextAgents, "create");
    },
    updateAgent() {
      if (!this.agentToEdit || !this.validateEditAgent()) {
        return;
      }

      const nextAgents = this.agents.map((agentData) => {
        if (agentData.id !== this.agentToEdit.id) {
          return agentData;
        }

        return {
          ...agentData,
          name: this.editAgentForm.name.trim(),
          role: this.editAgentForm.role,
          allowed_user: this.normalizeAllowedUser(
            this.editAgentForm.allowed_user
          ),
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

      const nextAgents = this.agents.filter((agentData) => {
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
      this.saveAgents(this.agents, "page");
    },
    configureModuleAborted() {
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
    goToCertificates() {
      this.core.$router.push("/settings/tls-certificates");
    },
    clearAllowedUsers() {
      this.agents = this.agents.map((agentData) => {
        return {
          ...agentData,
          allowed_user: "",
        };
      });
      this.createAgentForm.allowed_user = "";
      this.editAgentForm.allowed_user = "";
      this.clearCreateAgentErrors();
      this.clearEditAgentErrors();
    },
    sanitizeAllowedUsers() {
      const validUsers = new Set(this.domainUsers.map((userData) => userData.user));
      if (!validUsers.size) {
        return;
      }

      this.agents = this.agents.map((agentData) => {
        if (!agentData.allowed_user || validUsers.has(agentData.allowed_user)) {
          return agentData;
        }

        return {
          ...agentData,
          allowed_user: "",
        };
      });

      if (
        this.createAgentForm.allowed_user &&
        !validUsers.has(this.createAgentForm.allowed_user)
      ) {
        this.createAgentForm.allowed_user = "";
      }

      if (
        this.editAgentForm.allowed_user &&
        !validUsers.has(this.editAgentForm.allowed_user)
      ) {
        this.editAgentForm.allowed_user = "";
      }
    },
    onUserDomainChanged() {
      this.userDomain = this.normalizeUserDomain();
      this.error.userDomain = "";
      this.error.listDomainUsers = "";
      this.clearAllowedUsers();
      this.loadDomainUsers(this.userDomain);
    },
    async loadUserDomains() {
      this.loading.listUserDomains = true;
      this.error.listUserDomains = "";
      const taskAction = "list-user-domains";
      const eventId = this.getUuid();

      this.core.$root.$once(`${taskAction}-aborted-${eventId}`, () => {
        this.error.listUserDomains = this.$t("error.generic_error");
        this.loading.listUserDomains = false;
      });

      this.core.$root.$once(
        `${taskAction}-completed-${eventId}`,
        (taskContext, taskResult) => {
          this.userDomains = this.normalizeUserDomains(
            taskResult.output.domains || []
          );
          this.loading.listUserDomains = false;
        }
      );

      const res = await to(
        this.createModuleTaskForApp(this.instanceName, {
          action: taskAction,
          data: {},
          extra: {
            title: this.$t(`action.${taskAction}`),
            isNotificationHidden: true,
            eventId,
          },
        })
      );
      const err = res[0];

      if (err) {
        this.error.listUserDomains = this.getErrorMessage(err);
        this.loading.listUserDomains = false;
      }
    },
    async loadDomainUsers(domain) {
      const normalizedDomain = this.normalizeUserDomain(domain);
      this.domainUsers = [];
      this.error.listDomainUsers = "";

      if (!normalizedDomain) {
        return;
      }

      this.loading.listDomainUsers = true;
      const taskAction = "list-domain-users";
      const eventId = this.getUuid();

      this.core.$root.$once(`${taskAction}-aborted-${eventId}`, () => {
        if (normalizedDomain === this.normalizeUserDomain()) {
          this.error.listDomainUsers = this.$t("error.generic_error");
          this.loading.listDomainUsers = false;
        }
      });

      this.core.$root.$once(
        `${taskAction}-completed-${eventId}`,
        (taskContext, taskResult) => {
          if (normalizedDomain !== this.normalizeUserDomain()) {
            return;
          }

          this.domainUsers = this.normalizeDomainUsers(
            taskResult.output.users || []
          );
          this.loading.listDomainUsers = false;
          this.sanitizeAllowedUsers();
        }
      );

      const res = await to(
        this.createModuleTaskForApp(this.instanceName, {
          action: taskAction,
          data: {
            domain: normalizedDomain,
          },
          extra: {
            title: this.$t(`action.${taskAction}`),
            isNotificationHidden: true,
            eventId,
          },
        })
      );
      const err = res[0];

      if (err && normalizedDomain === this.normalizeUserDomain()) {
        this.error.listDomainUsers = this.getErrorMessage(err);
        this.loading.listDomainUsers = false;
      }
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";

.toolbar-row {
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

@media (max-width: 671px) {
  .toolbar-actions {
    justify-content: flex-start;
    margin-top: $spacing-05;
  }
}
</style>
