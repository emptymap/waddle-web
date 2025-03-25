import { createFileRoute, Link as RouterLink } from "@tanstack/react-router";
import { useEffect, useState, useCallback, useRef } from "react";
import {
	Box,
	Heading,
	Text,
	VStack,
	Spinner,
	Card,
	Flex,
	Button,
	Alert,
	Dialog,
	Steps,
	ProgressCircle,
} from "@chakra-ui/react";
import { toaster } from "../components/ui/toaster";
import {
	Check,
	AudioLines,
	Captions,
	FilePenLine,
	PlusCircle,
	Edit,
	Trash2,
	X,
	AlertTriangle,
	Clock,
} from "lucide-react";
import {
	type Episode,
	JobStatus,
	readEpisodesV1EpisodesGet,
	deleteEpisodeV1EpisodesEpisodeIdDelete,
} from "../client";

export const Route = createFileRoute("/")({
	component: Index,
});

function Index() {
	const [episodes, setEpisodes] = useState<Episode[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [episodeToDelete, setEpisodeToDelete] = useState<string | null>(null);
	const [episodeTitle, setEpisodeTitle] = useState<string | null>(null);
	const [isDialogOpen, setIsDialogOpen] = useState(false);
	const [isDeleting, setIsDeleting] = useState(false);

	// Ref for the cancel button to return focus to
	const cancelRef = useRef(null);

	const fetchEpisodes = useCallback(async () => {
		try {
			setLoading(true);
			const response = await readEpisodesV1EpisodesGet();
			if (response.error) {
				throw new Error("Failed to fetch episodes");
			}

			const sortedEpisodes = [...(response.data || [])].sort((a, b) => {
				const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
				const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
				return dateB - dateA;
			});

			setEpisodes(sortedEpisodes);
		} catch (err) {
			setError(
				err instanceof Error ? err.message : "An unknown error occurred",
			);
		} finally {
			setLoading(false);
		}
	}, []);

	useEffect(() => {
		fetchEpisodes();

		const POLLING_INTERVAL = 5000;
		const intervalId = setInterval(() => {
			console.log("Polling for new episodes...");
			fetchEpisodes();
		}, POLLING_INTERVAL);

		return () => clearInterval(intervalId);
	}, [fetchEpisodes]);

	const handleDeleteClick = (episodeId: string, title?: string) => {
		setEpisodeToDelete(episodeId);
		setEpisodeTitle(title || "Untitled Episode");
		setIsDialogOpen(true);
	};

	const confirmDelete = async () => {
		if (!episodeToDelete) return;

		try {
			setIsDeleting(true);
			const response = await deleteEpisodeV1EpisodesEpisodeIdDelete({
				path: { episode_id: episodeToDelete },
			});

			if (response.error) {
				throw new Error("Failed to delete episode");
			}

			// Update local state to remove the deleted episode
			setEpisodes(
				episodes.filter((episode) => episode.uuid !== episodeToDelete),
			);

			// Show success notification
			toaster.create({
				description: `Episode "${episodeTitle}" deleted successfully`,
				type: "success",
			});
		} catch (err) {
			toaster.create({
				description:
					err instanceof Error ? err.message : "Failed to delete episode",
				type: "error",
			});
		} finally {
			setIsDeleting(false);
			setIsDialogOpen(false);
			setEpisodeToDelete(null);
			setEpisodeTitle(null);
		}
	};

	const formatDate = (dateString?: string) => {
		if (!dateString) return "Unknown date";
		return new Date(dateString).toLocaleString(undefined, {
			year: "numeric",
			month: "short",
			day: "numeric",
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
		});
	};

	// Calculate the current step for each episode
	const getEpisodeStep = (episode: Episode) => {
		if (episode.metadata_generation_status === JobStatus.COMPLETED) return 3;
		if (episode.postprocess_status === JobStatus.COMPLETED) return 2;
		if (episode.preprocess_status === JobStatus.COMPLETED) return 1;
		return 0; // No steps complete
	};

	// Get status icon based on job status
	const getStatusIcon = (status?: JobStatus) => {
		switch (status) {
			case JobStatus.COMPLETED:
				return <Check />;
			case JobStatus.PENDING:
				return <Clock />;
			case JobStatus.FAILED:
				return <X />;
			case JobStatus.INIT:
				return null; // Use default icon for INIT status
			default:
				return null; // Use default icon for any other status
		}
	};

	// Define the processing steps
	const processingSteps = [
		{
			title: "Preprocess",
			description: "Initial data processing",
			icon: <AudioLines />,
			getStatus: (episode: Episode) => episode.preprocess_status,
		},
		{
			title: "Postprocess",
			description: "Transcript",
			icon: <Captions />,
			getStatus: (episode: Episode) => episode.postprocess_status,
		},
		{
			title: "Metadata",
			description: "Metadata generation",
			icon: <FilePenLine />,
			getStatus: (episode: Episode) => episode.metadata_generation_status,
		},
	];

	// Add this helper function before the return statement in your component
	const isEpisodeProcessing = (episode: Episode): boolean => {
		return (
			episode.preprocess_status === JobStatus.PROCESSING ||
			episode.postprocess_status === JobStatus.PROCESSING ||
			episode.metadata_generation_status === JobStatus.PROCESSING ||
			episode.preprocess_status === JobStatus.PENDING ||
			episode.postprocess_status === JobStatus.PENDING ||
			episode.metadata_generation_status === JobStatus.PENDING
		);
	};

	return (
		<Box p={4}>
			<Flex justifyContent="space-between" alignItems="center" mb={4}>
				<Heading size="lg">Episodes</Heading>
				<RouterLink to="/episodes/new">
					<Button>
						<PlusCircle size={16} /> New Episode
					</Button>
				</RouterLink>
			</Flex>

			{loading ? (
				<Flex justifyContent="center" p={8}>
					<Spinner size="xl" />
				</Flex>
			) : error ? (
				<Alert.Root status="error">
					<Alert.Indicator>
						<AlertTriangle />
					</Alert.Indicator>
					<Alert.Content>
						<Alert.Description>{error}</Alert.Description>
					</Alert.Content>
				</Alert.Root>
			) : episodes.length === 0 ? (
				<Text p={4}>No episodes found. Create your first episode!</Text>
			) : (
				<VStack gap={4} align="stretch">
					{episodes.map((episode) => (
						<Card.Root key={episode.uuid} variant="outline">
							<Card.Header>
								<Flex justifyContent="space-between" alignItems="center">
									<Heading size="md">
										{episode.title || "Untitled Episode"}
									</Heading>
									<Text fontSize="sm" color="gray.500">
										Created: {formatDate(episode.created_at)}
									</Text>
								</Flex>
							</Card.Header>
							<Card.Body>
								<Steps.Root
									step={getEpisodeStep(episode)}
									count={processingSteps.length}
									size="sm"
									variant="solid"
								>
									<Steps.List>
										{processingSteps.map((step, index) => {
											const status = step.getStatus(episode);
											return (
												<Steps.Item key={step.title} index={index} gap={2}>
													<Steps.Indicator>
														<Steps.Status
															incomplete={
																status === JobStatus.PROCESSING ? (
																	<ProgressCircle.Root value={null} size="sm">
																		<ProgressCircle.Circle>
																			<ProgressCircle.Track />
																			<ProgressCircle.Range />
																		</ProgressCircle.Circle>
																	</ProgressCircle.Root>
																) : (
																	getStatusIcon(status) || step.icon
																)
															}
															complete={<Check />}
														/>
													</Steps.Indicator>
													<Steps.Title>
														{step.title}{" "}
														{status &&
														status !== JobStatus.INIT &&
														status !== JobStatus.PROCESSING &&
														status !== JobStatus.COMPLETED ? (
															<Text as="span" fontSize="xs">
																({status})
															</Text>
														) : null}
													</Steps.Title>
													<Steps.Separator />
												</Steps.Item>
											);
										})}
									</Steps.List>
								</Steps.Root>
							</Card.Body>
							<Card.Footer>
								<Flex justifyContent="flex-end">
									{episode.uuid && (
										<RouterLink to={`/`}>
											{/* TODO: Replace `/episodes/${episode.uuid}` with the correct route */}
											<Button
												size="sm"
												mr={2}
												disabled={isEpisodeProcessing(episode)}
											>
												<Edit size={14} /> Edit
											</Button>
										</RouterLink>
									)}
									<Button
										size="sm"
										onClick={() =>
											episode.uuid &&
											handleDeleteClick(episode.uuid, episode.title)
										}
										disabled={isEpisodeProcessing(episode)}
									>
										<Trash2 size={14} /> Delete
									</Button>
								</Flex>
							</Card.Footer>
						</Card.Root>
					))}
				</VStack>
			)}

			{/* Delete Confirmation Dialog */}
			<Dialog.Root
				open={isDialogOpen}
				onOpenChange={({ open }) => setIsDialogOpen(open)}
				size="sm"
				placement="center"
				motionPreset="slide-in-bottom"
				role="alertdialog"
				closeOnEscape={false}
				closeOnInteractOutside={false}
				finalFocusEl={() => cancelRef.current}
			>
				<Dialog.Backdrop />
				<Dialog.Positioner>
					<Dialog.Content>
						<Dialog.CloseTrigger />
						<Dialog.Header>
							<Dialog.Title>Confirm Episode Deletion</Dialog.Title>
						</Dialog.Header>
						<Dialog.Body>
							<Text>
								Are you sure you want to delete "{episodeTitle}"? This action
								cannot be undone.
							</Text>
						</Dialog.Body>
						<Dialog.Footer>
							<Button
								ref={cancelRef}
								variant="outline"
								mr={3}
								onClick={() => setIsDialogOpen(false)}
								loading={isDeleting}
							>
								<X size={16} /> Cancel
							</Button>
							<Button
								colorPalette="red"
								onClick={confirmDelete}
								loading={isDeleting}
								loadingText="Deleting"
							>
								<Trash2 size={16} /> Delete
							</Button>
						</Dialog.Footer>
					</Dialog.Content>
				</Dialog.Positioner>
			</Dialog.Root>
		</Box>
	);
}
