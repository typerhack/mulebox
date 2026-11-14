// The page: the header, the out-of-step strip, the top row that every page keeps, and under
// it the view the hash names.

import { useEffect } from "react";

import { useRoute } from "./lib/router";
import { startLive } from "./state/live";
import { startStorage } from "./state/storage";
import { Header } from "./features/header/Header";
import { OutOfStepStrip } from "./features/header/OutOfStep";
import { HistoryPage } from "./features/history/HistoryPage";
import { JobPage } from "./features/job/JobPage";
import { JobsBox } from "./features/jobs/JobsBox";
import { MachinesPage } from "./features/machines/MachinesPage";
import { StatsPage } from "./features/stats/StatsPage";
import { StoragePage } from "./features/storage/StoragePage";
import { TopRow } from "./features/top/TopRow";
import { TipProvider } from "./ui/Tip";

export function App() {
  const route = useRoute();
  useEffect(() => startLive(), []);
  useEffect(() => startStorage(), []);
  return (
    <TipProvider>
      <Header page={route.page} />
      <main className="grid gap-gap px-gutter pt-gap pb-7">
        <OutOfStepStrip />
        <TopRow />
        {route.page === "job" ? <JobPage key={route.jobId} jobId={route.jobId} />
          : route.page === "machines" ? <MachinesPage />
          : route.page === "storage" ? <StoragePage />
            : route.page === "history" ? <HistoryPage />
              : route.page === "stats" ? <StatsPage /> : <JobsBox />}
      </main>
    </TipProvider>
  );
}
