import { createApp, analytics, files, genie, jobs, lakebase, server, type FilePolicy } from '@databricks/appkit';
import { setupStudyHubRoutes } from './routes/study-hub';

const landingPolicy: FilePolicy = (action, resource) => {
  if (action === 'upload') return /^SUB-[0-9A-Z-]+__[\w.-]+\.zip$/.test(resource.path);
  return action === 'exists' || action === 'metadata' || action === 'list';
};

createApp({
  plugins: [
    analytics(),
    files({ volumes: { files: { maxUploadSize: 500 * 1024 * 1024, policy: landingPolicy } } }),
    genie(),
    // "default" is DATABRICKS_JOB_ID (onboarding). It is only auto-discovered when no other job is bound, so name both.
    jobs({ jobs: { default: {}, manual_modelling: {} } }),
    lakebase(),
    server(),
  ],
  async onPluginsReady(appkit) {
    await setupStudyHubRoutes(appkit);
  },
}).catch(console.error);
