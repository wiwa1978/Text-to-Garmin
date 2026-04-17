targetScope = 'resourceGroup'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment. Used as a tag and as the seed for auto-generated resource names.')
param environmentName string

@minLength(1)
@description('Primary Azure region for all resources.')
param location string = resourceGroup().location

@description('Optional GitHub fine-grained PAT with the "Copilot Requests" permission. If empty, configure it via the in-app setup screen instead.')
@secure()
param copilotGithubToken string = ''

// ---------------------------------------------------------------------------
// Shared-password authentication.
// Leave appPassword empty to run without auth (only recommended if the app
// is not reachable from the public internet).
// ---------------------------------------------------------------------------
@description('Shared password for the web UI. Everyone who visits the URL must type it. Empty disables auth.')
@secure()
param appPassword string = ''

@description('Signing secret for session cookies (>=32 random chars). Leave empty to auto-generate a stable value.')
@secure()
param appSessionSecret string = ''

// ---------------------------------------------------------------------------
// Optional resource-name overrides. Leave empty to use an auto-generated name
// of the form "<abbr><hash>". Override any of them from main.parameters.json
// or via `azd env set <KEY> <value>`.
// ---------------------------------------------------------------------------
@description('Override the Azure Container Registry name (5-50 chars, alphanumeric, globally unique). Empty = auto-generated.')
param containerRegistryName string = ''

@description('Override the Container App name. Empty = auto-generated.')
param containerAppName string = ''

@description('Override the Container Apps managed environment name. Empty = auto-generated.')
param containerAppsEnvironmentName string = ''

@description('Override the Log Analytics workspace name. Empty = auto-generated.')
param logAnalyticsWorkspaceName string = ''

@description('Override the user-assigned managed identity name. Empty = auto-generated.')
param managedIdentityName string = ''

@description('Override the Storage Account name (3-24 chars, lowercase alphanumeric, globally unique). Empty = auto-generated.')
param storageAccountName string = ''

@description('Name of the Azure Files share mounted at /data inside the container.')
param fileShareName string = 'data'

@description('CPU cores allocated to the Container App (e.g. 0.25, 0.5, 1.0).')
param containerCpu string = '0.5'

@description('Memory allocated to the Container App (e.g. 0.5Gi, 1Gi, 2Gi).')
param containerMemory string = '1Gi'

@description('Minimum number of Container App replicas. "0" enables scale-to-zero.')
param minReplicas string = '0'

@description('Maximum number of Container App replicas.')
param maxReplicas string = '1'

var abbrs = {
  containerAppsEnvironment: 'cae-'
  containerApp: 'ca-'
  containerRegistry: 'cr'
  logAnalyticsWorkspace: 'log-'
  managedIdentity: 'id-'
  storageAccount: 'st'
}

var resourceToken = toLower(uniqueString(subscription().id, resourceGroup().id, environmentName))
var tags = {
  'azd-env-name': environmentName
}

var names = {
  identity: empty(managedIdentityName) ? '${abbrs.managedIdentity}${resourceToken}' : managedIdentityName
  logAnalytics: empty(logAnalyticsWorkspaceName) ? '${abbrs.logAnalyticsWorkspace}${resourceToken}' : logAnalyticsWorkspaceName
  containerAppsEnv: empty(containerAppsEnvironmentName) ? '${abbrs.containerAppsEnvironment}${resourceToken}' : containerAppsEnvironmentName
  containerApp: empty(containerAppName) ? '${abbrs.containerApp}${resourceToken}' : containerAppName
  containerRegistry: empty(containerRegistryName) ? '${abbrs.containerRegistry}${resourceToken}' : containerRegistryName
  storage: empty(storageAccountName) ? '${abbrs.storageAccount}${resourceToken}' : storageAccountName
}

// ---------------------------------------------------------------------------
// Identity (used by the Container App to pull from ACR)
// ---------------------------------------------------------------------------
resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.identity
  location: location
  tags: tags
}

// ---------------------------------------------------------------------------
// Log Analytics + Container Apps environment
// ---------------------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: names.logAnalytics
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: names.containerAppsEnv
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Storage account + Azure Files share for /data persistence
// ---------------------------------------------------------------------------
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: names.storage
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    largeFileSharesState: 'Enabled'
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource dataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: fileShareName
  properties: {
    shareQuota: 5
    enabledProtocols: 'SMB'
  }
}

resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerAppsEnv
  name: 'data'
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: dataShare.name
      accessMode: 'ReadWrite'
    }
  }
}

// ---------------------------------------------------------------------------
// Azure Container Registry + AcrPull for the app identity
// ---------------------------------------------------------------------------
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: names.containerRegistry
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

// AcrPull role definition id
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, appIdentity.id, acrPullRoleId)
  scope: containerRegistry
  properties: {
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

// ---------------------------------------------------------------------------
// Container App
// ---------------------------------------------------------------------------
var hasCopilotToken = !empty(copilotGithubToken)
var hasPassword = !empty(appPassword)
var effectiveSessionSecret = empty(appSessionSecret) ? uniqueString(subscription().id, resourceGroup().id, environmentName, 'session') : appSessionSecret

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: names.containerApp
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${appIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: appIdentity.id
        }
      ]
      secrets: concat(
        hasCopilotToken ? [
          {
            name: 'copilot-github-token'
            value: copilotGithubToken
          }
        ] : [],
        hasPassword ? [
          {
            name: 'app-password'
            value: appPassword
          }
          {
            name: 'app-session-secret'
            value: effectiveSessionSecret
          }
        ] : []
      )
    }
    template: {
      containers: [
        {
          name: 'web'
          // azd replaces this placeholder image with the freshly built one.
          image: 'mcr.microsoft.com/k8se/quickstart:latest'
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: concat(
            [
              {
                name: 'PORT'
                value: '8080'
              }
              {
                name: 'TEXT_TO_GARMIN_STATE_DIR'
                value: '/data'
              }
              {
                name: 'GARMINTOKENS'
                value: '/data/garmin_tokens.json'
              }
              {
                name: 'TEXT_TO_GARMIN_STATIC_DIR'
                value: '/app/static'
              }
            ],
            hasCopilotToken ? [
              {
                name: 'COPILOT_GITHUB_TOKEN'
                secretRef: 'copilot-github-token'
              }
            ] : [],
            hasPassword ? [
              {
                name: 'APP_PASSWORD'
                secretRef: 'app-password'
              }
              {
                name: 'APP_SESSION_SECRET'
                secretRef: 'app-session-secret'
              }
            ] : []
          )
          volumeMounts: [
            {
              volumeName: 'data'
              mountPath: '/data'
            }
          ]
        }
      ]
      scale: {
        minReplicas: int(minReplicas)
        maxReplicas: int(maxReplicas)
      }
      volumes: [
        {
          name: 'data'
          storageType: 'AzureFile'
          storageName: envStorage.name
        }
      ]
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs consumed by azd
// ---------------------------------------------------------------------------
output AZURE_LOCATION string = location
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.properties.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistry.name
output AZURE_CONTAINER_APPS_ENVIRONMENT_ID string = containerAppsEnv.id
output AZURE_CONTAINER_APP_NAME string = containerApp.name
output SERVICE_WEB_NAME string = containerApp.name
output SERVICE_WEB_URI string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output SERVICE_WEB_IDENTITY_PRINCIPAL_ID string = appIdentity.properties.principalId
