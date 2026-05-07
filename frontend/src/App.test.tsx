import { render, screen } from '@testing-library/react'
import { App } from './App'
import React from 'react'
import { describe, it, expect } from 'vitest'

describe('App', ()=>{
  it('renders greeting', ()=>{
    render(<App />)
    expect(screen.getByText(/Skill Factory/)).toBeTruthy()
  })
})
