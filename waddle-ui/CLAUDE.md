# Waddle UI Development Guidelines

## Commands
- `pnpm dev` - Start development server
- `pnpm build` - Build for production (runs TypeScript and Vite build)
- `pnpm lint` - Run ESLint on all files
- `pnpm preview` - Preview production build
- `pnpm generate-client` - Generate API client from OpenAPI spec

## Code Style
- **TypeScript**: Strict type checking with no unused variables/parameters
- **Formatting**: 2-space indentation, no semicolons preferred
- **Imports**: Group imports by source (React first, then external libraries, then internal)
- **Components**: Use named exports; functional components with React.forwardRef when needed
- **Routing**: Follow TanStack Router patterns for route definitions
- **UI Components**: Use Chakra UI, following wrapper pattern for custom components
- **Error Handling**: Use try/catch with proper type guards for error objects

## Architecture
- React 19 with Vite for build tooling
- TanStack Router for client-side routing
- Chakra UI for component library
- Generated API clients in src/client folder