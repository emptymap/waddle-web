import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { createRouter, RouterProvider } from "@tanstack/react-router";
import { Provider } from "./components/ui/provider.tsx";

import { Toaster } from "./components/ui/toaster.tsx";
import { routeTree } from "./routeTree.gen";

const router = createRouter({ routeTree });

// Register the router instance for type safety
declare module "@tanstack/react-router" {
	interface Register {
		router: typeof router;
	}
}

const root = document.getElementById("root");

if (root) {
	createRoot(root).render(
		<StrictMode>
			<Provider>
				<RouterProvider router={router} />
				<Toaster />
			</Provider>
		</StrictMode>,
	);
}
