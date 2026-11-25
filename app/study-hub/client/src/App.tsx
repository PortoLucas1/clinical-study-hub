import { createBrowserRouter, RouterProvider, NavLink, Outlet, Link } from 'react-router';
import { useState } from 'react';
import {
  Badge,
  Button,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  useIsMobile,
} from '@databricks/appkit-ui/react';
import { Menu, UploadCloud, UserCircle2 } from 'lucide-react';
import { PERSONA_LABEL, PersonaProvider, usePersona, type Persona } from './lib/persona';
import { useSubmissions } from './lib/submissions';
import { PortfolioPage } from './pages/PortfolioPage';
import { OnboardPage } from './pages/OnboardPage';
import { ApprovalsPage } from './pages/ApprovalsPage';
import { StudyPage } from './pages/StudyPage';

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `relative inline-flex h-full items-center gap-1.5 px-3 text-[15px] transition-colors after:absolute after:inset-x-3 after:-bottom-px after:h-0.5 after:rounded-full ${
    isActive ? 'text-primary after:bg-primary' : 'text-foreground hover:text-primary after:bg-transparent'
  }`;

const mobileNavLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
    isActive ? 'bg-secondary text-primary' : 'text-foreground hover:bg-muted'
  }`;

type NavLinkClassFn = (props: { isActive: boolean }) => string;

function NavLinks({ className, linkClass, onClick }: { className?: string; linkClass: NavLinkClassFn; onClick?: () => void }) {
  const { persona } = usePersona();
  const { submissions } = useSubmissions(15000);
  const pending = submissions.filter((s) => s.status === 'PENDING_APPROVAL').length;
  return (
    <nav className={className}>
      <NavLink to="/" end className={linkClass} onClick={onClick}>
        Study Portfolio
      </NavLink>
      <NavLink to="/onboard" className={linkClass} onClick={onClick}>
        Study Startup
      </NavLink>
      {persona === 'admin' && (
        <NavLink to="/approvals" className={linkClass} onClick={onClick}>
          Approvals
          {pending > 0 && (
            <Badge variant="destructive" className="h-5 min-w-5 justify-center px-1.5 text-[10px]">
              {pending}
            </Badge>
          )}
        </NavLink>
      )}
    </nav>
  );
}

function PersonaSwitcher() {
  const { persona, setPersona, email } = usePersona();
  return (
    <div className="flex items-center gap-2">
      <Select value={persona} onValueChange={(v) => setPersona(v as Persona)}>
        <SelectTrigger className="h-9 w-48 text-xs" aria-label="Persona">
          <UserCircle2 className="h-4 w-4 text-primary" />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(PERSONA_LABEL) as Persona[]).map((p) => (
            <SelectItem key={p} value={p}>
              {PERSONA_LABEL[p]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Badge variant="outline" className="hidden max-w-56 truncate xl:inline-flex" title="Signed-in user">
        {email ?? 'local developer'}
      </Badge>
    </div>
  );
}

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-4" aria-label="Clinical Study Hub home">
      <img src="/brand/helix_icon.svg" alt="Helix Clinical Research" className="h-9 w-9" />
      <span className="h-8 w-px bg-border" />
      <span className="text-[15px] font-semibold leading-tight text-foreground">
        Helix Study Hub
        <span className="block text-[11px] font-normal text-muted-foreground">Clinical Data Hub</span>
      </span>
    </Link>
  );
}

function AnnouncementBar() {
  return (
    <div className="brand-announce flex items-center justify-center gap-3 px-4 py-1.5 text-xs font-semibold">
      <span>Study onboarding, automated data quality and AI insights — powered by the Databricks Data Intelligence Platform</span>
      <span className="brand-pill hidden rounded px-2.5 py-0.5 sm:inline">Demo</span>
    </div>
  );
}

function Layout() {
  const isMobile = useIsMobile();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <AnnouncementBar />
      <header className="sticky top-0 z-30 border-b border-primary/30 bg-card/95 backdrop-blur">
        <div className="mx-auto flex h-[72px] max-w-7xl items-center gap-6 px-4 md:px-6">
          <Logo />
          <NavLinks className="hidden h-full md:flex" linkClass={navLinkClass} />
          <div className="ml-auto hidden items-center gap-3 md:flex">
            <PersonaSwitcher />
            <Button asChild className="shadow-md shadow-primary/30">
              <Link to="/onboard">
                <UploadCloud className="mr-1.5 h-4 w-4" /> Onboard a Study
              </Link>
            </Button>
          </div>
          <div className="ml-auto md:hidden">
            <Sheet open={mobileNavOpen && isMobile} onOpenChange={setMobileNavOpen}>
              <Button variant="ghost" size="icon" onClick={() => setMobileNavOpen(true)}>
                <Menu className="h-5 w-5" />
                <span className="sr-only">Open navigation</span>
              </Button>
              <SheetContent side="left">
                <SheetHeader>
                  <SheetTitle>
                    <img src="/brand/helix_icon.svg" alt="Helix Clinical Research" className="h-7 w-7" />
                  </SheetTitle>
                </SheetHeader>
                <div className="space-y-4 px-4">
                  <NavLinks className="flex flex-col gap-1" linkClass={mobileNavLinkClass} onClick={() => setMobileNavOpen(false)} />
                  <PersonaSwitcher />
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      <main className="flex-1 p-4 md:p-8">
        <Outlet />
      </main>
      <footer className="brand-footer">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-6 text-xs md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <img src="/brand/helix_icon.svg" alt="Helix Clinical Research" className="h-7 w-7" />
            <span>Clean study data, ready for review sooner.</span>
          </div>
          <div>
            Synthetic demo data · Built on Databricks Lakeflow, Unity Catalog, Lakebase, Genie and Apps
            {import.meta.env.VITE_APP_VERSION ? ` · build ${import.meta.env.VITE_APP_VERSION}` : ''}
          </div>
        </div>
      </footer>
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <PortfolioPage /> },
      { path: '/onboard', element: <OnboardPage /> },
      { path: '/approvals', element: <ApprovalsPage /> },
      { path: '/studies/:studyId', element: <StudyPage /> },
    ],
  },
]);

export default function App() {
  return (
    <PersonaProvider>
      <RouterProvider router={router} />
    </PersonaProvider>
  );
}
