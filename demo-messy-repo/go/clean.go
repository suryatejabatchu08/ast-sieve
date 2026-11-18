package main

import "log"

func handle(err error) {
	if err != nil {
		log.Println(err)
	}
}

func Add(a, b int) int {
	return a + b
}
