describe("Episodes Page", () => {
	beforeEach(() => {
		cy.visit("/");
	});

	it("should display the episodes page with correct title", () => {
		cy.contains("Episodes").should("be.visible");
		cy.contains("New Episode").should("be.visible");
	});

	it("should navigate to about page", () => {
		cy.visit("/about");
		cy.contains('Hello "/about"!').should("be.visible");
	});

	it("should show no episodes message when empty", () => {
		// Mock empty episodes response
		cy.intercept("GET", "**/v1/episodes/", {
			fixture: "empty-episodes.json",
		}).as("getEpisodes");

		cy.visit("/");
		cy.wait("@getEpisodes");

		cy.contains("No episodes found. Create your first episode!").should(
			"be.visible",
		);
	});

	it("should display episodes when data is available", () => {
		// Mock episodes response with sample data
		cy.intercept("GET", "**/v1/episodes/", { fixture: "episodes.json" }).as(
			"getEpisodes",
		);

		cy.visit("/");
		cy.wait("@getEpisodes");

		cy.contains("Test Episode 1").should("be.visible");
		cy.contains("Edit").should("be.visible");
		cy.contains("Delete").should("be.visible");
	});
});
