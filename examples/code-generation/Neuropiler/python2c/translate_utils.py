#!/usr/bin/env python
# -*- coding: utf-8 -*-
from . import blocks

class SupportedFunctions:

    functions = {}
    random_seed=1234
    def __init__(self):
        self.functions = {
        "randint": self.random_function,
        "random": self.random_function
    }

    def random_function(self, min, max):
        """
        Return a random function block for given random variables.
        """

        arg_blocks = [
            blocks.ExprBlock("int", "tid", is_arg=True),
            blocks.ExprBlock("unsigned long", "seed", is_arg=True)]
        template_blocks = [blocks.StringBlock()]
        template_blocks.append(blocks.StringBlock("curandState state;"))
        template_blocks.append(blocks.StringBlock("curand_init(seed, tid, 0, &state);"))
        template_blocks.append(blocks.StringBlock("return min + curand_uniform(&state)*(max - min);"))
        main_block = blocks.FunctionBlock(
            "__device__ float", "random", arg_blocks, sticky_front=template_blocks, function_ind=12, description="Random Generator Implementation"
        )
        main_block.should_indent = True
        return main_block



