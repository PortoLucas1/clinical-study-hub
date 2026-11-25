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
    jobs(),
    lakebase(),
    server(),
  ],
  async onPluginsReady(appkit) {
    await setupStudyHubRoutes(appkit);
  },
}).catch(console.error);
