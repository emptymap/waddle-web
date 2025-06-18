/// <reference types="cypress" />
describe("Simple E2E Test (Create and Delete)", () => {
	beforeEach(() => {
		cy.visit("/");
	});

	it("should create a new episode with audio files and delete it", () => {
		cy.contains("Episodes").should("be.visible");
		cy.get("body").should("not.contain", "Failed to fetch");

		// Create a new episode
		cy.contains("New Episode").click();
		cy.get('input[placeholder*="title"], input[name*="title"]').type(
			"Test Episode E2E",
		);
		// biome-ignore lint/style/useNodejsImportProtocol: Cypress doesn't support node: protocol
		const path = require("path");
		const audioFileNames = [
			"ep12-kotaro.wav",
			"GMT20250119-015233_Recording_1280x720.wav",
		];
		const audioFiles = audioFileNames.map((fileName) =>
			path.resolve(
				Cypress.config("projectRoot"),
				"..",
				"waddle-api",
				"tests",
				"ep0",
				fileName,
			),
		);
		cy.get('input[type="file"]').selectFile(audioFiles, { force: true });
		cy.contains("Create Episode").click();

		cy.get('[data-part="circle-track"]').should("be.visible"); // Loading indicator

		// Wait for the new episode to appear and have its preprocess completed
		cy.contains("Test Episode E2E")
			.parents('[class*="chakra-card__root"]')
			.within(() => {
				cy.get(".lucide-check", { timeout: 12000 }).should(
					"have.length.at.least",
					1,
				);
			}); // Wait for the preprocess to complete

		cy.screenshot("episode-created-with-preprocess-complete");

		cy.contains("Test Episode E2E")
			.parents('[class*="chakra-card__root"]')
			.find("button")
			.contains("Delete")
			.click();
		cy.get('[data-scope="dialog"]').should("be.visible");
		cy.get('[data-scope="dialog"]').find("button").contains("Delete").click();

		cy.contains("Test Episode E2E").should("not.exist");
	});
});
