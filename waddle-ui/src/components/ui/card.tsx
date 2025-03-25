import { Card as ChakraCard, forwardRef } from "@chakra-ui/react"
import * as React from "react"

export interface CardProps extends ChakraCard.RootProps {
  // Add any additional props specific to your card component
}

export const Card = Object.assign(
  forwardRef<CardProps, "div">((props, ref) => {
    const { children, ...rest } = props
    return (
      <ChakraCard.Root ref={ref} {...rest}>
        {children}
      </ChakraCard.Root>
    )
  }),
  {
    Root: ChakraCard.Root,
    Header: ChakraCard.Header,
    Body: ChakraCard.Body,
    Footer: ChakraCard.Footer,
  }
)