// Thrown into a request that was waiting for the server when the user moved to another screen.
export class RequestCancelled extends Error {
  constructor() {
    super('The request was cancelled because you left the screen.');
    this.name = 'RequestCancelled';
  }
}

export const isRequestCancelled = (err) => err instanceof RequestCancelled;
