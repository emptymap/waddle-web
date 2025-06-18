import { defaultPlugins } from "@hey-api/openapi-ts";

export default {
	input: "http://127.0.0.1:8000/openapi.json",
	output: {
		format: "biome",
		lint: "biome",
		path: "./src/client",
	},
	plugins: [
		...defaultPlugins,
		"@hey-api/client-fetch",
		{
			enums: "typescript",
			name: "@hey-api/typescript",
		},
	],
};
